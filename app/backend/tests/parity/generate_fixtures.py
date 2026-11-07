"""Generates the parity test's synthetic dictionary and question list, deterministically.

    python -m tests.parity.generate_fixtures            # writes tests/fixtures/parity/
    python -m tests.parity.generate_fixtures --check    # fails when the files differ

The dictionary is invented (no institution data) but shaped like a warehouse dictionary so
every rule of the parser and the engine has something to act on: Turkish letters and İ/ı,
compound and underscore names, a name with a trailing space, one table name in two schemas,
a table wider than 90 columns, tables without a profile, a synonym listed by more than 40
columns, roles and summaries, a "bazlı değil"
scope note, narrow-population tables, period and daily time columns, customer keys, product
breakdown columns in long and wide format, the legacy ``DAtabaseName`` header, a repeated
column row, an incomplete row, a blank row, number cells and extra sheet columns.

The workbook's zip entries carry a fixed time and its document properties fixed dates, so the
same generator gives the same parts; ``--check`` compares the parts, not the zip bytes (zlib
builds may compress differently).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "parity"
WORKBOOK = FIXTURES / "sozluk_sentetik.xlsx"
QUESTIONS = FIXTURES / "sorular.yaml"
FIXED_TIME = dt.datetime.fromisoformat("2026-10-08T09:00:00")  # document dates are naive

DB, ERP = "SYNDM", "SYNERP"


@dataclass(frozen=True, slots=True)
class Col:
    name: str
    description: str | int
    synonyms: str = ""
    role: str = ""
    summary: str | float = ""
    note: str = ""  # an extra column of the sheet ("Notlar")


@dataclass(slots=True)
class Table:
    db: str
    schema: str
    name: str
    group: str
    domain: str
    description: str  # "" and no profile row when ``profile`` is False
    grain: str
    time_columns: str
    key_columns: str
    columns: list[Col] = field(default_factory=list)
    profile: bool = True

    @property
    def key(self) -> str:
        return f"{self.db}.{self.schema}.{self.name}"


# --------------------------------------------------------------------------- column helpers


def key(name: str) -> Col:
    return KEYS[name]


KEYS = {
    "CustomerPartyId": Col(
        "CustomerPartyId",
        "Müşterinin veri ambarındaki tekil anahtarı (SKEY).",
        "müşteri SKEY, party id, müşteri anahtarı.",
        "Anahtar",
        "Müşteri SKEY",
    ),
    "CustomerId": Col(
        "CustomerId",
        "Müşteri numarası (CIF).",
        "müşteri no, CIF, hesap no",
        "Anahtar",
        "Müşteri numarası",
    ),
    "MainCustomerId": Col(
        "MainCustomerId",
        "Asıl kart sahibinin müşteri numarası.",
        "asıl müşteri no",
        "Anahtar",
        "Asıl kart müşterisi",
    ),
    "AccountNumber": Col(
        "AccountNumber",
        "Hesap numarası.",
        "hesap no, account number",
        "Anahtar",
        "Hesap no",
    ),
    "AccountSuffix": Col("AccountSuffix", "Hesap ek numarası.", "ek no", "Kod", "Hesap eki"),
    "CardRefNumber": Col(
        "CardRefNumber",
        "Kartın tekil referans numarası.",
        "kart referans no",
        "Anahtar",
        "Kart referansı",
    ),
    "ContractId": Col(
        "ContractId",
        "Fon kullandırım sözleşmesinin numarası.",
        "sözleşme no",
        "Anahtar",
        "Sözleşme no",
    ),
    "Period": Col(
        "Period",
        "Dönem (YYYYMM); ay sonu görüntüsü.",
        "dönem, ay yıl, YYYYMM",
        "Zaman",
        "Dönem · YYYYMM",
    ),
    "DataDate": Col(
        "DataDate",
        "Verinin ait olduğu gün (günlük görüntü).",
        "veri tarihi, iş tarihi",
        "Zaman",
        "Veri tarihi · günlük",
    ),
    "TranDate": Col(
        "TranDate",
        "İşlemin yapıldığı tarih.",
        "işlem tarihi, tran date",
        "Zaman",
        "İşlem tarihi",
    ),
    "ReportDate": Col("ReportDate", "Raporun tarihi.", "rapor tarihi", "Zaman", "Rapor tarihi"),
    "KKB_DATE": Col(
        "KKB_DATE",
        "KKB sorgusunun yapıldığı tarih.",
        "KKB tarihi",
        "Zaman",
        "KKB sorgu tarihi",
    ),
    "BranchCode": Col("BranchCode", "Şube kodu.", "şube kodu, branch", "Kod", "Şube kodu"),
    "CurrencyCode": Col(
        "CurrencyCode",
        "Para birimi (FEC) kodu.",
        "döviz cinsi, FEC",
        "Kod",
        "Para birimi",
    ),
}

PRODUCTS = (
    ("Consumer", "ihtiyaç kredisi"),
    ("HousingFinance", "konut finansmanı (gayrimenkul)"),
    ("VehicleFinance", "taşıt finansmanı"),
    ("Card", "kredi kartı"),
    ("Overdraft", "kredili mevduat hesabı (KMH)"),
    ("Commercial", "ticari fon kullandırım"),
    ("Leasing", "icare (leasing)"),
    ("Gold", "altın hesabı"),
    ("Fx", "döviz hesabı"),
    ("Cheque", "çek karnesi"),
)
MEASURES = (
    ("Balance", "bakiyesi", "bakiye, tutar", "Ölçü", "TL"),
    ("Limit", "tanımlı limiti", "limit", "Ölçü", "TL"),
    ("OverdueAmount", "gecikmiş tutarı", "gecikme tutarı, tutar", "Ölçü", "TL"),
    ("Count", "adedi", "adet, sayı", "Ölçü", "adet"),
)


def measure_columns(
    prefixes: Iterable[tuple[str, str]],
    measures: Sequence[tuple[str, ...]],
    whose: str = "Müşterinin",
) -> list[Col]:
    out = []
    for code, text in prefixes:
        for m_code, m_text, synonyms, role, unit in measures:
            out.append(
                Col(
                    f"{code}{m_code}",
                    f"{whose} {text} {m_text} ({unit}).",
                    f"{text} {m_text.split()[-1]}, {synonyms}",
                    role,
                    f"{text} {m_text} · {unit}"[:70],
                )
            )
    return out


def window_columns(
    metrics: Sequence[tuple[str, str]], windows: Sequence[tuple[str, str]]
) -> list[Col]:
    out = []
    for code, text in metrics:
        for w_code, w_text in windows:
            out.append(
                Col(
                    f"{code}{w_code}",
                    f"Kartın {w_text} {text}.",
                    f"{text}, {w_text} {text.split()[-1]}",
                    "Ölçü",
                    f"{text} · {w_text}"[:70],
                )
            )
    return out


def simple(*items: tuple[str, str, str, str]) -> list[Col]:
    """(name, description, synonyms, role) -> columns with a summary from the description."""
    return [Col(n, d, s, r, d.rstrip(".").split(";")[0][:70]) for n, d, s, r in items]


# --------------------------------------------------------------------------- tables


def tables() -> list[Table]:
    t: list[Table] = []

    def add(table: Table, *columns: Col | list[Col]) -> Table:
        for c in columns:
            table.columns.extend(c if isinstance(c, list) else [c])
        t.append(table)
        return table

    add(
        Table(
            DB,
            "CUS",
            "vCustomerInfo",
            "Müşteri",
            "Müşteri",
            "Bireysel ve tüzel bütün müşterilerin künye bilgileri.",
            "Müşteri",
            "DataDate",
            "CustomerPartyId",
        ),
        key("CustomerPartyId"),
        key("CustomerId"),
        key("BranchCode"),
        simple(
            (
                "CustomerName",
                "Müşterinin adı soyadı veya unvanı; KVKK kapsamında kişisel veri.",
                "müşteri adı, unvan (tüzel)",
                "Ad",
            ),
            ("BirthDate", "Müşterinin doğum tarihi. Kişisel veri.", "doğum tarihi", "Zaman"),
            (
                "Tenure",
                "Müşterilik süresi (yıl): bankaya ilk kayıttan bu yana geçen süre.",
                "müşterilik yaşı, kıdem, müşterilik kıdemi",
                "Ölçü",
            ),
            (
                "SegmentName",
                "Müşterinin segmenti (Bireysel, KOBİ, Ticari, Kurumsal).",
                "segment, müşteri sınıfı",
                "Ad",
            ),
            ("CustomerTypeName", "Bireysel / tüzel ayrımı.", "müşteri tipi", "Ad"),
            (
                "EmployerSectorName",
                "Bireysel müşterinin çalıştığı işverenin sektörü.",
                "işveren sektörü",
                "Ad",
            ),
            ("CityName", "Müşterinin ikamet ettiği il.", "il, şehir", "Ad"),
            ("GenderCode", "Cinsiyet kodu; KVKK kapsamında.", "cinsiyet", "Kod"),
            ("EducationLevelName", "Öğrenim durumu.", "eğitim", "Ad"),
            ("RecordingTime", "Müşterinin bankaya ilk kayıt zamanı.", "kayıt tarihi", "Zaman"),
            (
                "IsActiveCustomer",
                "Son 6 ayda işlem yapan müşteri bayrağı.",
                "aktif müşteri",
                "Bayrak",
            ),
        ),
        key("DataDate"),
    )
    add(
        Table(
            DB,
            "CUS",
            "vCustomerDetail",
            "Müşteri",
            "Müşteri",
            "Tüzel müşterilerin sektör ve firma bilgileri.",
            "Müşteri × Dönem",
            "Period",
            "CustomerPartyId, Period",
        ),
        key("CustomerPartyId"),
        key("Period"),
        simple(
            (
                "CompanySectorCode",
                "Firmanın faaliyet gösterdiği sektörün kodu.",
                "sektör kodu",
                "Kod",
            ),
            ("CompanySectorName", "Firmanın faaliyet sektörü.", "sektör, faaliyet alanı", "Ad"),
            ("SubSectorName", "Alt sektör.", "alt sektör", "Ad"),
            ("NaceCode", "NACE faaliyet kodu.", "NACE", "Kod"),
            ("CompanyFoundationDate", "Firmanın kuruluş tarihi.", "kuruluş tarihi", "Zaman"),
            (
                "CompanySectorAge",
                "Firmanın sektördeki yaşı (yıl); müşterinin yaşı değildir.",
                "firma yaşı",
                "Ölçü",
            ),
            ("EmployeeCount", "Firmanın çalışan sayısı.", "çalışan sayısı", "Ölçü"),
        ),
    )
    add(
        Table(
            DB,
            "PRC",
            "vCustomerGeneralInfo",
            "Müşteri",
            "Müşteri",
            "Müşteri bazında aylık özet: sektör, mevduat ve fon kullandırım toplamları "
            "birlikte.",
            "Müşteri × Dönem",
            "Period",
            "CustomerPartyId, Period",
        ),
        key("CustomerPartyId"),
        key("Period"),
        simple(
            (
                "CompanySectorCodeCurrP",
                "Dönem sonundaki firma sektörü kodu.",
                "sektör, sektör kodu",
                "Kod",
            ),
            (
                "TotalDeposit",
                "Müşterinin dönem sonu toplam mevduatı (TL).",
                "toplam mevduat, toplanan fon, tutar",
                "Ölçü",
            ),
            (
                "DemandDeposit",
                "Vadesiz (cari hesap) mevduat (TL).",
                "cari hesap, vadesiz, tutar",
                "Ölçü",
            ),
            (
                "TimeDeposit",
                "Vadeli (katılma hesabı) mevduat (TL).",
                "katılma hesabı, tutar",
                "Ölçü",
            ),
            (
                "TotalFundUsage",
                "Toplam fon kullandırım bakiyesi (TL).",
                "kredi bakiyesi, tutar",
                "Ölçü",
            ),
            ("CustomerAgeMonth", "Kişinin yaşı (ay); müşterilik süresi değildir.", "yaş", "Ölçü"),
            ("SegmentCode", "Segment kodu.", "segment", "Kod"),
        ),
    )
    add(
        Table(
            DB,
            "CUS",
            "vStrategicValue",
            "Müşteri",
            "Müşteri",
            "Müşterinin stratejik değer puanı ve müşterilik kıdemi.",
            "Müşteri × Dönem",
            "Period",
            "CustomerPartyId",
        ),
        key("CustomerPartyId"),
        key("Period"),
        simple(
            ("TenureMonth", "Müşterilik süresi (ay).", "kıdem, müşterilik yaşı", "Ölçü"),
            ("StrategicValueScore", "Stratejik değer puanı (0-100).", "değer puanı", "Ölçü"),
            ("ValueSegmentName", "Değer segmenti.", "değer segmenti", "Ad"),
        ),
    )
    add(
        Table(
            DB,
            "CUS",
            "vCustomerContact",
            "Müşteri",
            "Müşteri",
            "Müşteri iletişim bilgileri; kişisel veri içerir.",
            "Müşteri",
            "",
            "CustomerPartyId",
        ),
        key("CustomerPartyId"),
        simple(
            (
                "PhoneNumber",
                "Cep telefonu numarası; KVKK kapsamında kişisel veri.",
                "telefon, GSM",
                "Metin",
            ),
            ("EmailAddress", "E-posta adresi.", "e-posta, kişisel veri", "Metin"),
            (
                "AddressText",
                "Açık adres. KVKK kapsamında değildir diye işaretlenmemeli.",
                "adres",
                "Metin",
            ),
            ("ContactPermissionFlag", "Ticari ileti izni.", "izin", "Bayrak"),
        ),
    )
    card = add(
        Table(
            DB,
            "CRD",
            "vCardList",
            "Kart",
            "Kart",
            "Kart başına bir satır: kartın künyesi, statüsü ve asıl/ek kart ayrımı.",
            "Kart",
            "DataDate",
            "CardRefNumber",
        ),
        key("CardRefNumber"),
        Col(
            "CustomerId",
            "Ek kart sahibinin müşteri numarası; asıl müşteri değildir.",
            "kart sahibi",
            "Anahtar",
            "Ek kart sahibi",
        ),
        key("MainCustomerId"),
        simple(
            (
                "CardStatusCodeName",
                "Kartın güncel statüsü (açık, kapalı, iptal).",
                "kart statüsü",
                "Ad",
            ),
            ("CardBrandName", "Kart markası.", "marka", "Ad"),
            ("CardProductName", "Kart ürünü adı.", "kart ürünü", "Ad"),
            ("CardProductNumberName", "Kart ürün numarası ve adı.", "ürün no", "Ad"),
            ("IsMainCard", "Asıl kart bayrağı.", "asıl kart", "Bayrak"),
            ("CardOpenDate", "Kartın açılış tarihi.", "açılış tarihi", "Zaman"),
            ("CardCloseDate", "Kartın kapanış tarihi.", "kapanış tarihi", "Zaman"),
        ),
        key("DataDate"),
    )
    card.columns.append(
        Col("CardColourName", "Kartın rengi (klasik, altın, platin).", "renk", "Ad", "Kart rengi")
    )
    add(
        Table(
            DB,
            "CRD",
            "vCardLimitUsage",
            "Kart",
            "Kart",
            "Kart bazında günlük limit doluluğu.",
            "Kart × Gün",
            "DataDate",
            "CardRefNumber, DataDate",
        ),
        key("CardRefNumber"),
        key("CustomerPartyId"),
        key("DataDate"),
        Col(
            "CardLimitUsageToday",
            "Kartın bugünkü limit doluluk oranıdır.",
            "limit doluluk, kart kullanım oranı, utilization (kart bazlı), fullness.",
            "Ölçü",
            "Limit doluluk oranı · %",
        ),
        Col(
            "TotalLimitUsage",
            "Toplam limit doluluğu. Kart bazlı değil, müşterinin tüm limitlerini kapsar.",
            "toplam limit doluluğu",
            "Ölçü",
            "Tüm limitlerin doluluğu",
        ),
        Col(
            "CardLimitAmount",
            "Kartın tanımlı limiti (TL).",
            "kart limiti, tutar",
            "Ölçü",
            "Kart limiti · TL",
        ),
        Col(
            "UsedAmount",
            "Kullanılan tutar (TL).",
            "kullanılan limit, tutar",
            "Ölçü",
            "Kullanılan tutar · TL",
        ),
    )
    add(
        Table(
            DB,
            "CRD",
            "vCardLimit",
            "Kart",
            "Kart",
            "Kartların limit tanımları ve limit değişiklikleri.",
            "Kart × Dönem",
            "Period",
            "CardRefNumber",
        ),
        key("CardRefNumber"),
        key("Period"),
        simple(
            ("CardLimit", "Kartın tanımlı limiti (TL).", "kart limiti, limit, tutar", "Ölçü"),
            (
                "CardLimitRatio",
                (
                    "Kart limitinin referans değere oranı; doluluk oranı değildir. KVKK kapsamında "
                    "değildir."
                ),
                "limit oranı",
                "Ölçü",
            ),
            ("LimitChangeDate", "Son limit değişikliği tarihi.", "limit değişikliği", "Zaman"),
            ("LimitChangeReasonName", "Limit değişikliğinin nedeni.", "neden", "Ad"),
        ),
    )
    add(
        Table(
            DB,
            "CRD",
            "vCardBalanceSummary",
            "Kart",
            "Kart",
            "Kart bazında aylık ekstre ve bakiye özeti.",
            "Kart × Dönem",
            "Period",
            "CardRefNumber, Period",
        ),
        key("CardRefNumber"),
        key("CustomerPartyId"),
        key("Period"),
        simple(
            ("StatementBalance", "Ekstre borcu (TL).", "ekstre, borç, tutar", "Ölçü"),
            ("MinimumPayment", "Asgari ödeme tutarı (TL).", "asgari ödeme, tutar", "Ölçü"),
            ("CardOverdueAmount", "Gecikmiş kart borcu (TL).", "gecikmiş borç, tutar", "Ölçü"),
            ("InstallmentBalance", "Taksitli bakiye (TL).", "taksit, tutar", "Ölçü"),
            ("CashAdvanceBalance", "Nakit avans bakiyesi (TL).", "nakit avans, tutar", "Ölçü"),
        ),
    )
    add(
        Table(
            DB,
            "CRD",
            "vCardStatistic",
            "Kart",
            "Kart",
            "Kart kullanım istatistikleri: son 1, 3, 6 ve 12 ayın harcama ve işlem " "sayıları.",
            "Kart × Dönem",
            "Period",
            "CardRefNumber, Period",
        ),
        key("CardRefNumber"),
        key("Period"),
        window_columns(
            (
                ("TransactionCount", "işlem sayısı"),
                ("SpendAmount", "harcama tutarı"),
                ("CashAdvanceAmount", "nakit avans tutarı"),
                ("OnlineSpendAmount", "internet harcama tutarı"),
                ("InstallmentAmount", "taksitli harcama tutarı"),
            ),
            (
                ("L1M", "son 1 ay"),
                ("L3M", "son 3 ay"),
                ("L6M", "son 6 ay"),
                ("L12M", "son 12 ay"),
                ("L24M", "son 24 ay"),
                ("YTD", "yılbaşından bu yana"),
            ),
        ),
        Col(
            "Avg30dBalance",
            "Son 30 günün ortalama bakiyesi (TL).",
            "ortalama bakiye, tutar",
            "Ölçü",
            "30 gün ortalama bakiye",
        ),
    )
    add(
        Table(
            DB,
            "TRX",
            "vCardTurnover",
            "Kart",
            "Kart",
            "Kart işlemleri (turnover): işlem başına bir satır.",
            "İşlem",
            "TranDate",
            "CardRefNumber, TranDate",
        ),
        key("CardRefNumber"),
        key("TranDate"),
        simple(
            ("TrnAmount", "Kart işlem tutarı (TL).", "işlem tutarı, turnover, tutar", "Ölçü"),
            ("MerchantCategoryName", "Üye işyeri kategorisi (MCC).", "MCC, sektör", "Ad"),
            ("InstallmentCount", "Taksit sayısı.", "taksit", "Ölçü"),
            ("İşlemKanalıAdı", "İşlemin yapıldığı kanal (POS, internet, ATM).", "kanal", "Ad"),
            ("IsForeignTransaction", "Yurt dışı işlem bayrağı.", "yurt dışı", "Bayrak"),
        ),
    )
    transfer_types = (
        ("EFT", "EFT"),
        ("FAST", "FAST"),
        ("Havale", "havale"),
        ("SWIFT", "SWIFT"),
        ("Virman", "virman (banka içi hesaplar arası)"),
        ("Moneygram", "Moneygram"),
    )
    add(
        Table(
            DB,
            "TRX",
            "vCustomerMoneyTransferSummary",
            "İşlem",
            "İşlem",
            "Müşteri bazında aylık para transferi özeti: gelen ve giden transferlerin "
            "adet ve tutarları.",
            "Müşteri × Dönem × Transfer tipi",
            "Period",
            "CustomerPartyId, Period",
        ),
        key("CustomerPartyId"),
        key("AccountNumber"),
        key("Period"),
        Col(
            "TransferTypeName",
            "Transferin yönü: gelen / giden.",
            "transfer tipi, tür",
            "Ad",
            "Gelen / giden",
        ),
        measure_columns(
            transfer_types,
            (
                ("Count", "adedi", "transfer adedi, adet", "Ölçü", "adet"),
                ("AmountTL", "tutarı", "transfer tutarı, tutar", "Ölçü", "TL"),
                ("OriginalAmount", "orijinal döviz tutarı", "tutar", "Ölçü", "FEC"),
            ),
            whose="Ay içindeki",
        ),
        simple(
            (
                "OwnAccountTransferCount",
                "Kendi hesabına yapılan transfer adedi.",
                "kendi hesabına transfer",
                "Ölçü",
            ),
            (
                "OwnAccountTransferAmountTL",
                "Kendi hesabına transfer tutarı (TL).",
                "kendi hesabına transfer, tutar",
                "Ölçü",
            ),
            ("SWIFTCountL12M", "Son 12 ayın SWIFT adedi.", "SWIFT", "Ölçü"),
        ),
    )
    add(
        Table(
            DB,
            "TRX",
            "vFASTOutgoing",
            "İşlem",
            "İşlem",
            "Giden FAST transferleri: transfer başına bir satır.",
            "Transfer",
            "TranDate",
            "AccountNumber, TranDate",
        ),
        key("AccountNumber"),
        key("TranDate"),
        simple(
            (
                "ReceiverIdentityNumber",
                "Alıcının kimlik numarası; KVKK kapsamında kişisel veri.",
                "alıcı, lehtar",
                "Anahtar",
            ),
            ("ReceiverBankName", "Alıcı banka.", "alıcı banka, karşı banka", "Ad"),
            ("TransferAmount", "Transfer tutarı (TL).", "tutar", "Ölçü"),
            ("IsOwnAccount", "Kendi hesabına transfer bayrağı.", "kendi hesabı", "Bayrak"),
            ("ChannelName", "İşlem kanalı.", "kanal", "Ad"),
        ),
    )
    for name, text in (
        ("vEFTIncoming", "Gelen EFT"),
        ("vSwiftTransfer", "SWIFT transferleri"),
        ("vHavaleTransaction", "Havale işlemleri"),
    ):
        add(
            Table(
                DB,
                "TRX",
                name,
                "İşlem",
                "İşlem",
                f"{text}: işlem başına bir satır.",
                "İşlem",
                "TranDate",
                "AccountNumber",
            ),
            key("AccountNumber"),
            key("TranDate"),
            key("CurrencyCode"),
            simple(
                ("SenderName", "Gönderenin adı; kişisel veri.", "gönderen", "Ad"),
                ("TransferAmount", f"{text} tutarı (TL).", "tutar", "Ölçü"),
                ("TransferDescription", "Açıklama metni.", "açıklama", "Metin"),
                ("CounterBankName", "Karşı banka.", "karşı banka", "Ad"),
            ),
        )
    for name, text in (("vAtmTransaction", "ATM"), ("vPosTransaction", "POS")):
        add(
            Table(
                DB,
                "TRX",
                name,
                "İşlem",
                "İşlem",
                f"{text} işlemleri.",
                "İşlem",
                "TranDate",
                "AccountNumber",
            ),
            key("AccountNumber"),
            key("TranDate"),
            simple(
                (f"{text.title()}Id", f"{text} cihazının kimliği.", text, "Kod"),
                ("TransactionAmount", f"{text} işlem tutarı (TL).", "işlem tutarı, tutar", "Ölçü"),
                ("ChannelName", "İşlem kanalı.", "kanal", "Ad"),
            ),
        )
    add(
        Table(
            DB,
            "RSK",
            "vRiskProductMonthly",
            "Risk",
            "Risk",
            "Müşteri ve ürün bazında aylık risk: her ürün bir satır (uzun biçim).",
            "Müşteri × Dönem × Ürün",
            "Period",
            "CustomerPartyId, Period, ProductName",
        ),
        key("CustomerPartyId"),
        key("Period"),
        simple(
            (
                "ProductName",
                "Ürün adı (kredi kartı, konut, taşıt, ihtiyaç…).",
                "ürün, ürün adı",
                "Ad",
            ),
            ("FINANCETYPE", "Finansman tipi kodu.", "finansman tipi", "Kod"),
            ("RiskAmountTL", "Toplam risk tutarı (TL).", "risk, tutar", "Ölçü"),
            ("CashRiskTL", "Nakdi risk (TL).", "nakdi risk, tutar", "Ölçü"),
            ("NonCashRiskTL", "Gayrinakdi risk (TL).", "gayrinakdi risk, tutar", "Ölçü"),
            ("OverdueDays", "Gecikme gün sayısı (DPD).", "gecikme, DPD", "Ölçü"),
        ),
    )
    add(
        Table(
            DB,
            "MDL",
            "vRiskArrayAllotment",
            "Risk",
            "Risk",
            "Müşteri bazında aylık risk dizisi: her ürünün bakiye, limit, gecikme ve adet "
            "bilgileri ayrı kolonlarda (geniş biçim).",
            "Müşteri × Dönem",
            "Period",
            "CustomerPartyId, Period",
        ),
        key("CustomerPartyId"),
        key("Period"),
        measure_columns(PRODUCTS, MEASURES),
    )
    add(
        Table(
            DB,
            "MDL",
            "vRiskArrayCard",
            "Risk",
            "Kart",
            "Kart riskinin aylık dizisi.",
            "Müşteri × Dönem",
            "Period",
            "CustomerPartyId",
        ),
        key("CustomerPartyId"),
        key("Period"),
        simple(
            (
                "CreditCardLimitRate",
                "Kredi kartı limit doluluk oranı (%).",
                "limit doluluk oranı, kart kullanım oranı",
                "Ölçü",
            ),
            ("CardBalance", "Kredi kartı bakiyesi (TL).", "kart bakiyesi, tutar", "Ölçü"),
            ("CardCount", "Kart adedi.", "kart sayısı", "Ölçü"),
        ),
    )
    add(
        Table(
            DB,
            "CON",
            "vProjectRisk",
            "Risk",
            "Risk",
            "Proje finansmanı riskleri: günlük, ürün adıyla.",
            "Proje × Gün",
            "DataDate",
            "ContractId",
        ),
        key("ContractId"),
        key("DataDate"),
        simple(
            ("ProductName", "Ürün adı.", "ürün", "Ad"),
            ("RiskAmountTL", "Risk tutarı (TL).", "risk, tutar", "Ölçü"),
            ("ProjectName", "Proje adı.", "proje", "Ad"),
        ),
    )
    add(
        Table(
            DB,
            "CON",
            "vIFRSAccountStatus",
            "Risk",
            "Risk",
            "IFRS 9 hesap durumu: içsel derecelendirme notu, temerrüt olasılığı ve aşama.",
            "Hesap × Gün",
            "DataDate",
            "AccountNumber, ContractId",
        ),
        key("AccountNumber"),
        key("ContractId"),
        key("CustomerPartyId"),
        key("DataDate"),
        simple(
            (
                "CurrentCustomerGrade",
                "Müşterinin güncel içsel derecelendirme notu.",
                "rating, IDM, derecelendirme notu",
                "Kod",
            ),
            (
                "CurrentCustomerPD",
                "Güncel temerrüt olasılığı (PD).",
                "PD, temerrüt olasılığı",
                "Ölçü",
            ),
            ("IFRS9_STAGE", "IFRS 9 aşaması (1, 2, 3).", "stage, evre", "Kod"),
            ("StageChangeDate", "Aşama değişikliği tarihi.", "aşama değişikliği", "Zaman"),
        ),
    )
    add(
        Table(
            DB,
            "CON",
            "vExpectedCreditLoss",
            "Risk",
            "Risk",
            "Beklenen kredi zararı (ECL).",
            "Sözleşme × Dönem",
            "Period",
            "ContractId",
        ),
        key("ContractId"),
        key("Period"),
        simple(
            ("ECLAmount", "Beklenen kredi zararı (TL).", "ECL, karşılık, tutar", "Ölçü"),
            ("LifetimePD", "Ömür boyu PD.", "PD", "Ölçü"),
            ("LGD", "Temerrüt halinde kayıp oranı.", "LGD", "Ölçü"),
        ),
    )
    add(
        Table(
            DB,
            "CFM",
            "vFinanceCustomerDetail",
            "Risk",
            "Risk",
            "Finansman müşterilerinin KKB skoru ve demografik özeti.",
            "Müşteri",
            "KKB_DATE",
            "CustomerPartyId",
        ),
        key("CustomerPartyId"),
        key("KKB_DATE"),
        simple(
            (
                "CurrentKKBScore",
                "Güncel KKB (kredi kayıt bürosu) skoru.",
                "KKB skoru, findeks",
                "Ölçü",
            ),
            ("Age", "Kişinin yaşı (yıl).", "yaş", "Ölçü"),
            ("IncomeAmount", "Beyan edilen gelir (TL).", "gelir, tutar", "Ölçü"),
        ),
    )
    add(
        Table(
            DB,
            "IDM",
            "vKKBReport",
            "Risk",
            "Dış veri",
            "KKB raporu: bankalar arası toplam risk (memzuç) ve skor.",
            "Müşteri × Dönem",
            "KKB_DATE",
            "CustomerPartyId",
        ),
        key("CustomerPartyId"),
        key("KKB_DATE"),
        simple(
            ("KKBScore", "KKB skoru.", "KKB skoru", "Ölçü"),
            (
                "TotalBankRisk",
                "Bankacılık sistemindeki toplam risk (memzuç).",
                "memzuç, toplam risk, tutar",
                "Ölçü",
            ),
            ("OverdueAccountCount", "Gecikmeli hesap sayısı.", "gecikmeli hesap", "Ölçü"),
        ),
    )
    add(
        Table(
            DB,
            "EWS",
            "vTriggerValue",
            "Risk",
            "Risk",
            "Erken uyarı sistemi tetikleyici değerleri.",
            "Müşteri × Gün",
            "DataDate",
            "CustomerPartyId",
        ),
        key("CustomerPartyId"),
        key("DataDate"),
        simple(
            ("TriggerName", "Tetikleyici adı.", "erken uyarı, EWS", "Ad"),
            ("TriggerValue", "Tetikleyici değeri.", "değer", "Ölçü"),
            ("ColourName", "Erken uyarı rengi.", "renk, colour", "Ad"),
        ),
    )
    add(
        Table(
            DB,
            "RSK",
            "vNplFollowUp",
            "Risk",
            "Risk",
            "Donuk alacak (takipteki alacak) izleme.",
            "Sözleşme × Dönem",
            "Period",
            "ContractId",
        ),
        key("ContractId"),
        key("Period"),
        simple(
            ("NplAmountTL", "Takipteki alacak tutarı (TL).", "NPL, donuk alacak, tutar", "Ölçü"),
            ("FollowUpStartDate", "Takibe alınma tarihi.", "takip tarihi", "Zaman"),
            ("CollectionAmountTL", "Tahsilat tutarı (TL).", "tahsilat, tutar", "Ölçü"),
        ),
    )
    add(
        Table(
            DB,
            "MDL",
            "vCollateral",
            "Risk",
            "Risk",
            "Teminatlar.",
            "Teminat",
            "DataDate",
            "ContractId",
        ),
        key("ContractId"),
        key("DataDate"),
        simple(
            ("CollateralTypeName", "Teminat türü.", "teminat türü", "Ad"),
            ("CollateralAmountTL", "Teminat tutarı (TL).", "teminat, tutar", "Ölçü"),
        ),
    )
    add(
        Table(
            DB,
            "CON",
            "vAccountBalanceSummary",
            "Mevduat",
            "Mevduat",
            "Hesap bazında aylık bakiye özeti.",
            "Hesap × Dönem",
            "Period",
            "AccountNumber, AccountSuffix, Period",
        ),
        key("AccountNumber"),
        key("AccountSuffix"),
        key("CustomerPartyId"),
        key("Period"),
        key("CurrencyCode"),
        simple(
            ("AccountTypeName", "Hesap türü (vadesiz, vadeli/katılma).", "hesap türü", "Ad"),
            ("Balance", "Dönem sonu bakiye (orijinal döviz).", "bakiye, tutar", "Ölçü"),
            ("BalanceTL", "Dönem sonu bakiye (TL).", "bakiye, tutar", "Ölçü"),
            ("AverageBalanceTL", "Ortalama bakiye (TL).", "ortalama bakiye, tutar", "Ölçü"),
        ),
    )
    add(
        Table(
            DB,
            "CON",
            "vCustomerAssetDepositBalanceDaily",
            "Mevduat",
            "Mevduat",
            "Müşteri bazında günlük varlık ve mevduat bakiyeleri.",
            "Müşteri × Gün",
            "DataDate",
            "CustomerPartyId, DataDate",
        ),
        key("CustomerPartyId"),
        key("DataDate"),
        measure_columns(
            (
                ("Deposit", "mevduatı"),
                ("ParticipationAccount", "katılma hesabı"),
                ("DemandAccount", "cari hesabı"),
                ("GoldAccount", "altın hesabı"),
                ("Fx", "döviz hesabı"),
            ),
            (
                ("BalanceTL", "bakiyesi", "bakiye, tutar", "Ölçü", "TL"),
                ("Count", "adedi", "adet", "Ölçü", "adet"),
            ),
        ),
    )
    add(
        Table(
            DB,
            "DEP",
            "vParticipationAccount",
            "Mevduat",
            "Mevduat",
            "Katılma hesapları ve kâr payı oranları.",
            "Hesap",
            "DataDate",
            "AccountNumber",
        ),
        key("AccountNumber"),
        key("DataDate"),
        simple(
            ("ProfitShareRate", "Kâr payı oranı (%).", "kâr payı, faiz oranı", "Ölçü"),
            ("MaturityDays", "Vade gün sayısı.", "vade", "Ölçü"),
            ("PoolName", "Katılma havuzu adı.", "havuz", "Ad"),
        ),
    )
    add(
        Table(
            DB,
            "DEP",
            "vDemandDepositDaily",
            "Mevduat",
            "Mevduat",
            "Vadesiz mevduat günlük bakiyeleri.",
            "Hesap × Gün",
            "DataDate",
            "AccountNumber",
        ),
        key("AccountNumber"),
        key("DataDate"),
        simple(("DemandBalanceTL", "Vadesiz bakiye (TL).", "vadesiz, tutar", "Ölçü")),
    )
    for schema, desc in (
        ("CMP", "Kampanya tanımları ve hedef kitle sayıları."),
        ("CFM", "Finansman kampanyalarının yanıtları."),
    ):
        add(
            Table(
                DB,
                schema,
                "vCampaign",
                "Kampanya - Hedef Kitle",
                "Pazarlama",
                desc,
                "Kampanya",
                "",
                "CampaignId",
            ),
            simple(
                ("CampaignId", "Kampanya numarası.", "kampanya no", "Anahtar"),
                ("CampaignName", "Kampanya adı.", "kampanya", "Ad"),
                ("CampaignStartDate", "Başlangıç tarihi.", "başlangıç", "Zaman"),
                ("TargetAudienceCount", "Hedef kitledeki müşteri sayısı.", "hedef kitle", "Ölçü"),
            ),
            key("CustomerPartyId") if schema == "CFM" else [],
        )
    add(
        Table(
            DB,
            "CMP",
            "vSmartTargeting",
            "Kampanya - Hedef Kitle",
            "Pazarlama",
            "Akıllı hedefleme modelinin skorları; yalnız kampanya kitlesi.",
            "Müşteri",
            "Period",
            "CustomerPartyId",
        ),
        key("CustomerPartyId"),
        key("Period"),
        simple(
            ("CardPropensityScore", "Kredi kartı eğilim skoru.", "eğilim skoru", "Ölçü"),
            ("DepositPropensityScore", "Mevduat eğilim skoru.", "eğilim skoru", "Ölçü"),
        ),
    )
    add(
        Table(
            DB,
            "CMP",
            "vMarketingPermission",
            "Kampanya - Hedef Kitle",
            "Pazarlama",
            "Pazarlama izinleri.",
            "Müşteri",
            "",
            "CustomerPartyId",
        ),
        key("CustomerPartyId"),
        simple(
            ("SmsPermission", "SMS izni.", "izin", "Bayrak"),
            ("EmailPermission", "E-posta izni; kişisel veri.", "izin", "Bayrak"),
        ),
    )
    churn = add(
        Table(
            DB,
            "AIS",
            "vChurnModelInput",
            "Analitik",
            "Model",
            "Müşteri kaybı (churn) modeli girdisi; eğitim verisi. Bütün bankayı kapsamaz.",
            "Müşteri × Dönem",
            "Period",
            "CustomerPartyId, Period",
        ),
        key("CustomerPartyId"),
        key("Period"),
    )
    topics = (
        "kart işlem adedi",
        "mevduat bakiyesi",
        "kredi kartı sayısı",
        "şube ziyareti",
        "mobil giriş",
        "maaş ödemesi",
        "fatura ödemesi",
        "döviz işlemi",
        "ATM çekimi",
        "kampanya yanıtı",
        "müşterilik süresi",
    )
    for i in range(150):
        topic = topics[i % len(topics)]
        churn.columns.append(
            Col(
                f"Feature{i + 1:03d}",
                f"Model girdisi: {topic} (son {1 + i // 11} ay).",
                f"{topic}, model değişkeni",
                "Ölçü",
                f"Girdi · {topic}"[:70],
            )
        )
    add(
        Table(
            DB,
            "AIS",
            "vRetailChurnTrainingInput",
            "Analitik",
            "Model",
            "Bireysel churn modeli eğitim seti.",
            "Müşteri",
            "Period",
            "CustomerPartyId",
        ),
        key("CustomerPartyId"),
        key("Period"),
        simple(
            (
                "NumberOfCreditCards",
                "Müşterinin kredi kartı sayısı (model girdisi).",
                "kart sayısı",
                "Ölçü",
            ),
            ("TenureYear", "Müşterilik süresi (yıl, model girdisi).", "kıdem", "Ölçü"),
            ("ChurnFlag", "Müşteri kaybı etiketi.", "churn", "Bayrak"),
        ),
    )
    add(
        Table(
            DB,
            "AIS",
            "vCarOwnershipPrediction",
            "Analitik",
            "Model",
            "Araç sahipliği tahmin modeli girdisi.",
            "Müşteri",
            "Period",
            "CustomerPartyId",
        ),
        key("CustomerPartyId"),
        key("Period"),
        simple(
            (
                "CreditScore",
                "Model için hesaplanan kredi skoru (model girdisi).",
                "kredi skoru",
                "Ölçü",
            ),
            ("CarOwnershipProbability", "Araç sahibi olma olasılığı.", "olasılık", "Ölçü"),
        ),
    )
    add(
        Table(
            DB,
            "AIS",
            "vSegmentationInput",
            "Analitik",
            "Model",
            "Müşteri segmentasyonu girdisi.",
            "Müşteri",
            "Period",
            "CustomerPartyId",
        ),
        key("CustomerPartyId"),
        key("Period"),
        simple(
            ("BehaviourScore", "Davranış skoru (eğilim).", "davranış skoru", "Ölçü"),
            ("SegmentCandidateName", "Aday segment.", "segment", "Ad"),
        ),
    )
    add(
        Table(
            DB,
            "BDG",
            "vCustomerProfitabilityAllProduct",
            "Bütçe",
            "Karlılık",
            "Müşteri ve ürün bazında karlılık.",
            "Müşteri × Dönem × Ürün",
            "Period",
            "CustomerPartyId, Period",
        ),
        key("CustomerPartyId"),
        key("Period"),
        simple(
            ("ProductTypeName", "Ürün tipi.", "ürün tipi", "Ad"),
            ("ProfitAmountTL", "Karlılık tutarı (TL).", "kâr, tutar", "Ölçü"),
            ("DepositVolumeTL", "Mevduat hacmi (TL).", "mevduat, tutar", "Ölçü"),
        ),
    )
    add(
        Table(
            DB,
            "BRN",
            "vBranchPerformance",
            "Şube",
            "Organizasyon",
            "Şube bazında aylık performans.",
            "Şube × Dönem",
            "Period",
            "BranchCode",
        ),
        key("BranchCode"),
        key("Period"),
        simple(
            ("BranchName", "Şube adı.", "şube", "Ad"),
            ("NewCustomerCount", "Yeni müşteri sayısı.", "yeni müşteri", "Ölçü"),
            ("DepositVolumeTL", "Şube mevduat hacmi (TL).", "mevduat, tutar", "Ölçü"),
        ),
    )
    add(
        Table(
            DB,
            "PB",
            "vPrivateBankingCustomer",
            "Özel Bankacılık",
            "Müşteri",
            "Özel bankacılık müşterileri: varlık ve mevduat özeti.",
            "Müşteri × Dönem",
            "Period",
            "CustomerPartyId",
        ),
        key("CustomerPartyId"),
        key("Period"),
        simple(
            ("TotalAssetTL", "Toplam varlık (TL).", "varlık, tutar", "Ölçü"),
            ("TotalDepositTL", "Toplam mevduat (TL).", "mevduat, tutar", "Ölçü"),
            ("CompanySectorName", "Firma sektörü.", "sektör", "Ad"),
        ),
    )
    add(
        Table(
            ERP,
            "HRM",
            "vPersonKKB",
            "İnsan Kaynakları",
            "Personel",
            "Personelin KKB skoru (yalnız çalışanlar).",
            "Personel",
            "KKB_DATE",
            "PersonId",
        ),
        simple(
            ("PersonId", "Personel numarası.", "sicil", "Anahtar"),
            ("CurrentScore", "Personelin güncel KKB skoru.", "KKB skoru", "Ölçü"),
        ),
        key("KKB_DATE"),
    )
    add(
        Table(
            ERP,
            "HRM",
            "vEmployee",
            "İnsan Kaynakları",
            "Personel",
            "Personel bilgileri; kişisel veri.",
            "Personel",
            "",
            "PersonId",
        ),
        simple(
            ("PersonId", "Personel numarası.", "sicil", "Anahtar"),
            ("PersonName", "Personelin adı soyadı; KVKK kapsamında.", "ad soyad", "Ad"),
            ("DepartmentName", "Bölüm adı.", "bölüm", "Ad"),
        ),
    )
    for name, text, synonyms in (
        ("vLeasingContract", "İcare (leasing) sözleşmeleri", "icare, leasing, finansal kiralama"),
        ("vMurabahaContract", "Murabaha sözleşmeleri", "murabaha, vadeli satış"),
        ("vSukukHolding", "Kira sertifikası (sukuk) varlıkları", "sukuk, kira sertifikası"),
    ):
        add(
            Table(
                DB,
                "LSG",
                name,
                "Finansman",
                "Katılım",
                f"{text}.",
                "Sözleşme",
                "DataDate",
                "ContractId",
            ),
            key("ContractId"),
            key("CustomerPartyId"),
            key("DataDate"),
            simple(
                ("PrincipalAmountTL", f"{text} anapara tutarı (TL).", f"{synonyms}, tutar", "Ölçü"),
                ("ProfitRate", "Kâr payı oranı (%).", "kâr payı", "Ölçü"),
                ("MaturityDate", "Vade tarihi.", "vade", "Zaman"),
            ),
        )
    add(
        Table(
            DB,
            "FX",
            "vFxTransaction",
            "Hazine",
            "Döviz",
            "Döviz alım satım işlemleri.",
            "İşlem",
            "TranDate",
            "AccountNumber",
        ),
        key("AccountNumber"),
        key("TranDate"),
        key("CurrencyCode"),
        simple(
            ("FxAmount", "Döviz tutarı.", "döviz, tutar", "Ölçü"),
            ("ExchangeRate", "İşlem kuru.", "kur", "Ölçü"),
        ),
    )
    add(
        Table(
            DB,
            "INS",
            "vInsurancePolicy",
            "Sigorta",
            "Tekafül",
            "Tekafül (sigorta) poliçeleri.",
            "Poliçe",
            "DataDate",
            "PolicyId",
        ),
        simple(
            ("PolicyId", "Poliçe numarası.", "poliçe", "Anahtar"),
            ("PremiumAmountTL", "Prim tutarı (TL).", "prim, tutar", "Ölçü"),
        ),
        key("CustomerPartyId"),
        key("DataDate"),
    )
    add(
        Table(
            DB,
            "DGT",
            "vDigitalLogin",
            "Dijital",
            "Kanal",
            "İnternet ve mobil şube girişleri.",
            "Giriş",
            "TranDate",
            "CustomerPartyId",
        ),
        key("CustomerPartyId"),
        key("TranDate"),
        simple(
            ("ChannelName", "Kanal (internet, mobil).", "kanal, dijital şube", "Ad"),
            ("LoginCount", "Giriş sayısı.", "giriş", "Ölçü"),
        ),
    )
    add(
        Table(
            DB,
            "DGT",
            "vMobileTransaction",
            "Dijital",
            "Kanal",
            "Mobil işlemler.",
            "İşlem",
            "TranDate",
            "CustomerPartyId",
        ),
        key("CustomerPartyId"),
        key("TranDate"),
        simple(
            ("İşlemTürüAdı", "Mobil işlem türü.", "işlem türü", "Ad"),
            ("TransactionAmount", "İşlem tutarı (TL).", "tutar", "Ölçü"),
        ),
    )
    add(
        Table(
            DB, "BRN", "vBranch", "Şube", "Organizasyon", "Şube listesi.", "Şube", "", "BranchCode"
        ),
        key("BranchCode"),
        simple(
            ("BranchName", "Şube adı.", "şube", "Ad"),
            ("RegionName", "Bölge.", "bölge", "Ad"),
            ("CityName", "İl.", "il", "Ad"),
        ),
    )
    add(
        Table(DB, "BRN", "vAtmList", "Şube", "Organizasyon", "ATM listesi.", "ATM", "", "AtmId"),
        simple(
            ("AtmId", "ATM numarası.", "ATM", "Kod"), ("BranchCode", "Bağlı şube.", "şube", "Kod")
        ),
    )
    add(
        Table(
            DB,
            "CON",
            "vLoanApplication",
            "Finansman",
            "Kredi",
            "Fon kullandırım başvuruları.",
            "Başvuru",
            "TranDate",
            "ApplicationId",
        ),
        simple(
            ("ApplicationId", "Başvuru numarası.", "başvuru", "Anahtar"),
            ("ApplicationStatusName", "Başvuru durumu.", "durum", "Ad"),
            ("RequestedAmountTL", "Talep edilen tutar (TL).", "tutar", "Ölçü"),
        ),
        key("CustomerPartyId"),
        key("TranDate"),
    )
    add(
        Table(
            DB,
            "CON",
            "vLoanContract",
            "Finansman",
            "Kredi",
            "Fon kullandırım sözleşmeleri.",
            "Sözleşme",
            "DataDate",
            "ContractId",
        ),
        key("ContractId"),
        key("CustomerPartyId"),
        key("DataDate"),
        simple(
            ("ProductTypeName", "Ürün tipi (ihtiyaç, konut, taşıt).", "ürün tipi", "Ad"),
            ("PrincipalAmountTL", "Anapara (TL).", "anapara, tutar", "Ölçü"),
            ("ProfitRate", "Kâr payı oranı (%).", "kâr payı oranı", "Ölçü"),
            ("MaturityDate", "Vade tarihi.", "vade", "Zaman"),
        ),
    )
    add(
        Table(
            DB,
            "CON",
            "vLoanPayment",
            "Finansman",
            "Kredi",
            "Taksit ödemeleri.",
            "Taksit",
            "TranDate",
            "ContractId",
        ),
        key("ContractId"),
        key("TranDate"),
        simple(
            ("InstallmentAmountTL", "Taksit tutarı (TL).", "taksit, tutar", "Ölçü"),
            ("PaidAmountTL", "Ödenen tutar (TL).", "ödeme, tutar", "Ölçü"),
        ),
    )
    add(
        Table(
            DB,
            "TRX",
            "vChequeTransaction",
            "İşlem",
            "İşlem",
            "Çek işlemleri.",
            "Çek",
            "TranDate",
            "AccountNumber",
        ),
        key("AccountNumber"),
        key("TranDate"),
        simple(("ChequeAmountTL", "Çek tutarı (TL).", "çek, tutar", "Ölçü")),
    )
    add(
        Table(
            DB,
            "TRX",
            "vPosMerchant",
            "İşlem",
            "İşlem",
            "Üye işyerleri.",
            "İşyeri",
            "",
            "MerchantId",
        ),
        simple(
            ("MerchantId", "Üye işyeri numarası.", "işyeri", "Anahtar"),
            ("MerchantCategoryName", "Kategori (MCC).", "MCC", "Ad"),
        ),
    )
    add(
        Table(
            DB,
            "RPT",
            "rpt_DailyLiquidity",
            "Hazine",
            "Likidite",
            "Günlük likidite raporu.",
            "Gün",
            "ReportDate",
            "ReportDate",
        ),
        key("ReportDate"),
        simple(
            ("LiquidityRatio", "Likidite oranı.", "likidite oranı", "Ölçü"),
            ("CashAmountTL", "Nakit (TL).", "nakit, tutar", "Ölçü"),
        ),
    )
    add(
        Table(
            DB,
            "RPT",
            "rpt_MonthlyRiskReport",
            "Risk",
            "Risk",
            "Aylık risk raporu.",
            "Dönem",
            "Period",
            "Period",
        ),
        key("Period"),
        simple(
            ("TotalRiskTL", "Toplam risk (TL).", "toplam risk, tutar", "Ölçü"),
            ("NplRatio", "Takipteki alacak oranı.", "NPL oranı", "Ölçü"),
        ),
    )
    for name, columns in (
        (
            "vProductCatalog",
            simple(("ÜrünGrubu", "Ürün grubu.", "", ""), ("ProductCode", "Ürün kodu.", "", "")),
        ),
        ("vCurrencyRate", simple(("CurrencyRate", "Günlük kur.", "kur", "Ölçü"))),
        ("vHoliday", simple(("HolidayDate", "Resmi tatil günü.", "tatil", "Zaman"))),
    ):  # tables without a profile: the catalog lists their column names
        add(Table(DB, "REF", name, "", "", "", "", "", "", profile=False), columns, key("DataDate"))
    add(
        Table(
            DB,
            "MDL",
            "vCustomerMonthlyProfile",
            "Analitik",
            "Müşteri",
            "Müşteri bazında aylık ürün profili: güncel, 3 ve 12 aylık ortalama değerler.",
            "Müşteri × Dönem",
            "Period",
            "CustomerPartyId, Period",
        ),
        key("CustomerPartyId"),
        key("Period"),
        measure_columns(
            [
                (f"{p}{w}", f"{t} ({wt})")
                for w, wt in (("Cur", "güncel"), ("Avg3M", "3 ay ort."), ("Avg12M", "12 ay ort."))
                for p, t in PRODUCTS
            ],
            MEASURES[:3],
        ),
    )
    # A wide reporting set so the dictionary reaches the size of a real one.
    topics = (
        ("Branch", "şube"),
        ("Region", "bölge"),
        ("Segment", "segment"),
        ("Channel", "kanal"),
        ("Product", "ürün"),
        ("Sector", "sektör"),
        ("City", "il"),
        ("AgeBand", "yaş grubu"),
        ("Gender", "cinsiyet"),
        ("Tenure", "kıdem"),
        ("Campaign", "kampanya"),
        ("Currency", "para birimi"),
        ("Education", "eğitim"),
        ("Occupation", "meslek"),
        ("Income", "gelir grubu"),
        ("RiskGroup", "risk grubu"),
        ("Digital", "dijital kullanım"),
        ("Portfolio", "portföy"),
        ("Rating", "derece"),
        ("Vintage", "kuşak"),
        ("District", "ilçe"),
    )
    for topic, text in topics:
        add(
            Table(
                DB,
                "RPT",
                f"rpt_{topic}MonthlySummary",
                "Raporlama",
                "Rapor",
                f"{text.title()} bazında aylık yönetim raporu.",
                f"{text.title()} × Dönem",
                "Period",
                "Period",
            ),
            key("Period"),
            Col(f"{topic}Name", f"{text.title()} adı.", text, "Ad", f"{text.title()} adı"),
            measure_columns(PRODUCTS, MEASURES, whose=f"{text.title()} toplamı:"),
        )
    return t


# --------------------------------------------------------------------------- workbook

OBJECT_HEADER = (
    "ObjectKey",
    "DatabaseName",
    "SchemaName",
    "ObjectName",
    "ObjectDescription",
    "Grain",
    "KeyColumns",
    "TimeColumns",
    "BusinessDomain",
    "DatasetGroup",
    "Sahip",
)
COLUMN_HEADER = (
    "DAtabaseName",
    "Schema Name",
    "ObjectName",
    "ColumnName",
    "ColumnDescription",
    "Synonyms",
    "Role",
    "Summary",
    "Notlar",
)


def object_rows(all_tables: Sequence[Table]) -> list[list[object]]:
    rows: list[list[object]] = []
    for i, t in enumerate(all_tables):
        if not t.profile:
            continue
        key_cell = "" if i % 9 == 4 else t.key  # some rows give the parts instead of the key
        rows.append(
            [
                key_cell,
                t.db,
                t.schema,
                t.name,
                t.description,
                t.grain,
                t.key_columns,
                t.time_columns,
                t.domain,
                t.group,
                "Veri Ofisi" if i % 3 == 0 else None,
            ]
        )
    rows.append(
        [
            f"{DB}.OLD.vRetired",
            DB,
            "OLD",
            "vRetired",
            "Kullanımdan kalkmış tablo.",
            "",
            "",
            "",
            "",
            "Arşiv",
            None,
        ]
    )
    rows.append(
        [
            f"{DB}.CRD.vCardList",
            DB,
            "CRD",
            "vCardList",
            (
                "Kart başına bir satır: kartın künyesi, statüsü ve asıl/ek kart ayrımı "
                "(güncel tanım)."
            ),
            "Kart",
            "CardRefNumber",
            "DataDate",
            "Kart",
            "Kart",
            None,
        ]
    )
    rows.append(["", "", "", "", "Anahtarı olmayan satır.", "", "", "", "", "", None])
    return rows


def column_rows(all_tables: Sequence[Table]) -> list[list[object]]:
    rows: list[list[object]] = []
    for ti, t in enumerate(all_tables):
        for ci, c in enumerate(t.columns):
            name = c.name
            obj = t.name
            if t.name == "vCardLimitUsage" and ci == 1:
                name = f"{c.name} "  # a column name with a trailing space
            if t.name == "vCardLimitUsage" and ci == 2:
                obj = f"{t.name} "  # an object name with a trailing space
            synonyms: object = c.synonyms or None
            if c.role == "Ölçü" and "tutar" not in c.synonyms and (ti + ci) % 2 == 0:
                synonyms = f"{c.synonyms}, tutar" if c.synonyms else "tutar"
            rows.append(
                [
                    t.db,
                    t.schema,
                    obj,
                    name,
                    c.description,
                    synonyms,
                    c.role or None,
                    c.summary or None,
                    c.note or None,
                ]
            )
        if t.name == "vCardList":
            rows.append(
                [
                    t.db,
                    t.schema,
                    t.name,
                    "CardRefNumber",
                    "Tekrarlanan satır.",
                    None,
                    None,
                    None,
                    None,
                ]
            )
            rows.append([None, None, None, None, None, None, None, None, None])
            rows.append(
                [t.db, None, t.name, "Orphan", "Şeması eksik satır.", None, None, None, None]
            )
        if t.name == "vCustomerDetail":
            rows.append(
                [
                    t.db,
                    t.schema,
                    t.name,
                    "LegacyCode",
                    12345,
                    "eski kod",
                    "Kod",
                    3.0,
                    "sayı hücreleri",
                ]
            )
    return rows


def build_workbook() -> bytes:
    all_tables = tables()
    wb = Workbook()
    wb.remove(wb.active)
    objects = wb.create_sheet("Objeler")
    objects.append(list(OBJECT_HEADER))
    for row in object_rows(all_tables):
        objects.append(row)
    columns = wb.create_sheet("Kolonlar")
    columns.append(list(COLUMN_HEADER))
    for row in column_rows(all_tables):
        columns.append(row)
    wb.create_sheet("Açıklama").append(["Sentetik sözlük; fark testi için üretildi."])
    wb.properties.created = wb.properties.modified = FIXED_TIME
    raw = BytesIO()
    wb.save(raw)
    return _fixed_zip(raw.getvalue())


def _fixed_zip(data: bytes) -> bytes:
    """The workbook with fixed zip times and a fixed modification date (openpyxl writes the
    time of saving)."""
    stamp = FIXED_TIME.strftime("%Y-%m-%dT%H:%M:%SZ")
    out = BytesIO()
    with zipfile.ZipFile(BytesIO(data)) as src, zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            part = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                part = re.sub(
                    rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)",
                    rb"\g<1>" + stamp.encode() + rb"\g<2>",
                    part,
                )
            fixed = zipfile.ZipInfo(info.filename, date_time=FIXED_TIME.timetuple()[:6])
            fixed.compress_type = zipfile.ZIP_DEFLATED
            fixed.external_attr = 0o600 << 16
            dst.writestr(fixed, part)
    return out.getvalue()


def workbook_parts(data: bytes) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(BytesIO(data)) as z:
        return [(i.filename, z.read(i.filename)) for i in z.infolist()]


# --------------------------------------------------------------------------- questions

GOLDEN = (
    (
        "q001",
        (
            "Müşterilerin risk bilgilerini aylık bazda ve kırılımlı olarak (kredi kartı, "
            "gayrimenkul, ihtiyaç kredisi vb.) gösteren bir tablo mevcut mudur?"
        ),
    ),
    ("q002", "Kredi kartı limit doluluk oranı verisine ihtiyacımız var, nerede?"),
    (
        "q003",
        (
            "Müşteri bazında aylık para transferi özeti: transfer tipi, transfer adedi, toplam "
            "transfer tutarı TL, işlem yapılan farklı kişi sayısı, farklı banka sayısı, kendi "
            "hesabına transfer adedi ve tutarı"
        ),
    ),
    (
        "q001-kapsam",
        (
            "Müşterilerin risk bilgilerini aylık bazda ve kırılımlı olarak (kredi kartı, "
            "gayrimenkul, ihtiyaç kredisi vb.) gösteren bir tablo mevcut mudur?"
        ),
    ),
    ("q004", "Müşterinin kredi kartlarının bilgisi"),
    ("q005", "Müşterinin sektör bazlı mevduat dağılımı"),
    ("q006", "Müşterinin kredi risk skoru"),
    ("q007", "Müşterinin müşterilik yaşı"),
)
NEGATIVE = (
    ("n001", "Uzay gemisi yakıt seviyesi"),
    ("n002", "Futbol maçlarının skorları ve gol atan oyuncular"),
    ("n003", "Şehirlere göre günlük hava sıcaklığı tahmini"),
    ("n004", "Çalışanların yemekhane menü tercihleri"),
    ("n005", "Tarladaki buğday hasat nem ölçümü sensör verisi"),
)
SYNTHETIC = (
    # time
    "Aylık kredi kartı harcama tutarı",
    "Günlük mevduat bakiyesi nerede?",
    "Haftalık ATM çekim adedi",
    "Yıllık müşteri karlılığı",
    "Çeyreklik risk raporu",
    "Dönemsel şube performansı",
    "Ay sonu katılma hesabı bakiyesi",
    "monthly card spend amount",
    "daily deposit balance per customer",
    "Periyodik kampanya yanıtları",
    # breakdown and listed values
    "Ürün kırılımlı aylık risk (kredi kartı, konut kredisi, taşıt kredisi)",
    "Müşteri bazında kırılımlı risk (KMH, ihtiyaç kredisi vb.) tablosu",
    "Segment kırılımında mevduat dağılımı",
    "Şube detayında yeni müşteri sayısı",
    "Ürün breakdown risk amount (card, housing)",
    "Kırılımlı olarak (altın hesabı, döviz hesabı) günlük bakiyeler",
    # measures
    "Kart limit kullanım oranı",
    "Taksitli harcama yüzdesi",
    "Gecikmiş kart borcu tutarı",
    "Kredi kartı adedi",
    "Transfer sayısı ve tutarı",
    "Ortalama bakiye",
    "likidite oranı",
    "NPL oranı aylık",
    "Kâr payı oranı katılma hesabı",
    "Toplam risk bakiyesi",
    # negation
    "Kartı olmayan müşteriler",
    "Virman hariç para transferleri",
    "Kredi kartı değil banka kartı",
    "FAST dışında giden transferler",
    "Kart bazlı değil toplam limit doluluğu",
    "İzni olmayan müşterilerin kampanya yanıtı",
    "except FAST outgoing transfers",
    # numbers
    "Son 3 ay kart harcaması",
    "Son 6 ay kart harcaması",
    "Son 12 ayın SWIFT adedi",
    "2024 yılı mevduat bakiyesi",
    "30 günlük ortalama bakiye",
    "Son 1 ay nakit avans tutarı",
    # term-group equivalents
    "Fon kullandırım bakiyesi",
    "Kredi bakiyesi",
    "Kâr payı tutarı",
    "Faiz oranı",
    "Leasing sözleşmeleri",
    "İcare sözleşme tutarı",
    "Murabaha vadeli satış",
    "Sukuk varlıkları",
    "Kira sertifikası",
    "Müşteri numarası ile hesap numarası eşlemesi",
    "CIF bazında bakiye",
    "Hesap no ile kart eşleşmesi",
    "EFT ve havale adetleri",
    "Findeks skoru",
    "Kredi kayıt bürosu skoru",
    "Memzuç toplam risk",
    "Donuk alacak tutarı",
    "Takipteki alacak tahsilatı",
    "Temerrüt olasılığı",
    "İçsel derecelendirme notu",
    "IFRS 9 aşaması",
    "Teminat mektubu riski",
    "Nakit avans kullanımı",
    "Konut finansmanı bakiyesi",
    "Taşıt kredisi limiti",
    "KMH limiti",
    "Anlık transfer adedi",
    "Uluslararası transfer tutarı",
    "Kendi hesabına para transferi",
    "Kampanya hedef kitlesi",
    "Hedef kitle büyüklüğü",
    "Kart ciro hacmi",
    "harcama tutarı ciro",
    # exact column names
    "CardLimitUsageToday",
    "KKB_DATE",
    "IFRS9_STAGE",
    "CustomerPartyId",
    "SWIFTCountL12M",
    "Avg30dBalance",
    "TotalLimitUsage nedir?",
    "CreditCardLimitRate verisi",
    "Feature042",
    # no Turkish letters
    "musteri kredi karti limit doluluk orani",
    "ihtiyac kredisi bakiyesi aylik",
    "musterilik suresi",
    "sube bazinda yeni musteri sayisi",
    "kar payi orani",
    # upper case İ/ı
    "MÜŞTERİ İHTİYAÇ KREDİSİ RİSKİ",
    "KARTIN LİMİTİ VE DOLULUĞU",
    "IŞIK SEKTÖRÜ MÜŞTERİLERİ",
    "İŞLEM KANALI ADI",
    "ÜRÜNGRUBU",
    # punctuation only, conceptless
    "?!.,;",
    "— … —",
    "Merhaba",
    "ve ile için",
    "bir şey lazım",
    "nerede var mı",
    # table names
    f"{DB}.CRD.vCardList",
    "vCardList",
    "rpt_DailyLiquidity tablosu",
    f"{ERP}.HRM.vPersonKKB",
    "vCampaign",
    f"{DB}.REF.vHoliday",
    # personal data, narrow populations, scope notes
    "Müşteri adı soyadı ve telefon numarası",
    "Alıcı kimlik numarası",
    "TCKN listesi",
    "Özel bankacılık müşterilerinin mevduatı",
    "Churn modeli girdileri",
    "Akıllı hedefleme skoru",
    "Segmentasyon girdisi davranış skoru",
    "Personelin KKB skoru",
    "Virman tutarı müşteri bazında",
    "Kampanya kitlesindeki müşterilerin kart harcaması",
    # customer level and multi-concept
    "Müşteri bazında aylık kredi kartı ve mevduat bakiyesi",
    "Sektör ve segment bazında risk",
    "Şube ve bölge bazında mevduat hacmi",
    "Müşterinin yaşı ve müşterilik süresi",
    "Firma yaşı ve sektör",
    "Kart statüsü ve asıl kart sahibi",
    "Ek kart sahibi müşteri numarası",
    "Kredi kartı limit doluluk oranı ve gecikme gün sayısı",
    "Hesap türü bazında bakiye",
    "Döviz alım satım kuru ve tutarı",
    "Tekafül prim tutarı",
    "Mobil şube giriş sayısı",
    "Dijital kanal işlem türü",
    "Fon kullandırım başvuru durumu",
    "Taksit ödeme tutarı",
    "Çek tutarı aylık",
    "Üye işyeri kategorisi",
    "ATM listesi şube bazında",
    "Proje finansmanı riski",
    "Erken uyarı rengi",
    "Beklenen kredi zararı ECL",
    "Teminat türü ve tutarı",
    "Araç sahipliği tahmini",
    "Kart rengi",
    "Bölge bazında aylık yönetim raporu",
    "Kanal bazında ürün bakiyeleri",
    "credit card limit utilization",
    "customer churn score",
    "deposit balance by sector",
    "Kartın bugünkü limit doluluk oranı nedir ve hangi tabloda bulunur, kart bazlı mı?",
)
SCENARIO_QUESTIONS = (
    ("step1_failed", "Kredi kartı harcamaları aylık"),
    ("step2_failed", "Müşteri bazında mevduat bakiyesi"),
    ("no_candidates", "Uzay istasyonu oksijen seviyesi"),
    ("context_exceeded", "Kart limit doluluk oranı günlük"),
    ("timeout", "Para transferi adedi aylık"),
    ("connection_refused", "KKB skoru müşteri bazında"),
    ("http_500", "Katılma hesabı kâr payı"),
    ("server_down", "Kredi risk skoru"),
    ("server_unauthorized", "Şube performansı"),
    ("no_model", "Müşterilik süresi"),
    ("empty_dictionary", "Kredi kartı limiti"),
    ("server_down", "Mevduat dağılımı sektör bazlı"),
    ("http_500", "Ürün kırılımlı risk"),
)


def long_question() -> str:
    """A request close to the 4000-character limit."""
    sentence = (
        "Müşteri bazında aylık kredi kartı harcama tutarı, limit doluluk oranı ve "
        "gecikme gün sayısı (kart bazlı) ile mevduat bakiyesi gerekiyor. "
    )
    text = sentence * (3990 // len(sentence))
    return text.strip()[:3990]


def questions() -> list[tuple[str, str, str]]:
    items = [(f"g-{i}", q, "normal") for i, q in GOLDEN]
    items += [(f"n-{i}", q, "normal") for i, q in NEGATIVE]
    items += [(f"s{n:03d}", q, "normal") for n, q in enumerate(SYNTHETIC, 1)]
    items.append((f"s{len(SYNTHETIC) + 1:03d}", long_question(), "normal"))
    items += [(f"x{n:02d}", q, s) for n, (s, q) in enumerate(SCENARIO_QUESTIONS, 1)]
    return items


def questions_yaml() -> str:
    lines = [
        "# Fark testi soruları (question-analysis PRD, Test stratejisi): kaynak altın setinin 8",
        "# sorusu (batch maddesi b001 hariç), negatif setin 5 sorusu, sentetik sözlüğe yazılmış",
        "# sorular ve senaryolu sorular. tests/parity/generate_fixtures.py üretir; elle düzenlemeyin.",
    ]
    for qid, query, scenario in questions():
        lines.append(f"- id: {qid}")
        lines.append(f"  query: {json.dumps(query, ensure_ascii=False)}")
        if scenario != "normal":
            lines.append(f"  scenario: {scenario}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="compare with the committed files")
    args = parser.parse_args()
    workbook, text = build_workbook(), questions_yaml()
    if args.check:
        same = workbook_parts(workbook) == workbook_parts(WORKBOOK.read_bytes())
        same = same and QUESTIONS.read_text(encoding="utf-8") == text
        print("fixtures current" if same else "fixtures differ from the generator")
        return 0 if same else 1
    FIXTURES.mkdir(parents=True, exist_ok=True)
    WORKBOOK.write_bytes(workbook)
    QUESTIONS.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
