# Sözlük güncelleme raporu

- Sonuç: **completed**
- Başlangıç / bitiş (UTC): 2026-11-06 22:16 / 2026-11-06 22:29
- Önceki sürüm: `f90a96fb4cc8-11136`
- Yeni sürüm: `bf5c8d53d870-11752`
- Model: `google/gemma-4-26b-a4b-qat`, çağrı 57, hatalı 0
- Sözlükteki nesne ve kolon: 413 / 11752

## Özet

| Değişiklik | Adet |
|---|---:|
| Eklenen nesne | 27 |
| Silinen nesne | 4 |
| Ambarda bulunmayan nesne | 8 |
| Adı veya şeması düzeltilen nesne | 10 |
| Mevcut nesneye eklenen kolon | 66 |
| Silinen kolon | 79 |
| Ambarda bulunmayan kolon | 60 |
| Yazımı düzeltilen kolon | 138 |
| EDWUTIL'de olmayıp korunan kolon | 1 |
| Modelin doldurduğu alan | 3022 |
| Boş kalan alan | 57 |
| Toplam silinen kolon (silinen nesnelerin kolonları dahil) | 121 |

## Alan değişiklikleri

| Tür | Alan | Kaynak | Adet |
|---|---|---|---:|
| column_changed | Summary | model | 737 |
| column_changed | Role | model | 736 |
| column_changed | ColumnDescription | duzenleme | 712 |
| column_changed | Synonyms | model | 703 |
| column_changed | SchemaName | kaynak | 132 |
| column_changed | ColumnName | kaynak | 128 |
| column_changed | ColumnDescription | onceki | 125 |
| column_changed | Summary | onceki | 121 |
| column_changed | ObjectName | kaynak | 89 |
| table_changed | ObjectDescription | duzenleme | 27 |
| table_changed | Grain | model | 27 |
| table_changed | KeyColumns | model | 27 |
| table_changed | BusinessDomain | model | 27 |
| table_changed | TimeColumns | model | 26 |
| table_changed | ObjectKey | kaynak | 9 |
| table_changed | ObjectName | kaynak | 5 |
| table_changed | SchemaName | kaynak | 4 |
| column_changed | ColumnDescription | kaynak | 2 |
| column_changed | Summary | kaynak | 2 |

## Silinen nesne (4)

- `EDWBridge.SME.rpt_EDWWorkingDepthSegmentation`
- `EDWBridge.TRX.rpt_EDWCallHoldDetailReport`
- `EDWDM.CUS.vCustomerEfficiency`
- `EDWDM.CUS.vCustomerEfficiencyMonthly`

## Adı veya şeması düzeltilen nesne (10)

- `EDWBridge.CUS.rpt_EDWPrivateBankingCustomerAssetChangeReport` (`EDWBridge.TRX.rpt_EDWPrivateBankingCustomerAssetChangeReport` → `EDWBridge.CUS.rpt_EDWPrivateBankingCustomerAssetChangeReport`)
- `EDWBridge.CUS.rpt_EDWPrivateBankingCustomerReport` (`EDWBridge.TRX.rpt_EDWPrivateBankingCustomerReport` → `EDWBridge.CUS.rpt_EDWPrivateBankingCustomerReport`)
- `EDWBridge.TRX.rpt_EDWHighCashFlowCustomers` (`EDWBridge.TRX.rpt_HighCashFlowCustomers` → `EDWBridge.TRX.rpt_EDWHighCashFlowCustomers`)
- `EDWDM.AIS.vPFMMCCDescription` (`EDWDM.AIS.vPFMMccDescription` → `EDWDM.AIS.vPFMMCCDescription`)
- `EDWDM.CFM.vEcommerceRefund` (`EDWDM.CFM.vECommerceRefund` → `EDWDM.CFM.vEcommerceRefund`)
- `EDWDM.CMP.vPopUpResponseTargetDataInHours` (`EDWDM.CMP.vPopupResponseTargetDataInHours` → `EDWDM.CMP.vPopUpResponseTargetDataInHours`)
- `EDWDM.CMP.vPopUpResponseTargetDataInWeekDays` (`EDWDM.CMP.vPopupResponseTargetDataInWeekDays` → `EDWDM.CMP.vPopUpResponseTargetDataInWeekDays`)
- `EDWDM.CFM.vProjectPaybackPlanInstallment` (`EDWDM.PRC.vProjectPaybackPlanInstallment` → `EDWDM.CFM.vProjectPaybackPlanInstallment`)
- `EDWDM.CFM.vProposalPaybackPlanInstallment` (`EDWDM.PRC.vProposalPaybackPlanInstallment` → `EDWDM.CFM.vProposalPaybackPlanInstallment`)
- `EDWDM.TRX.vKasOutgoing` (`EDWDM.TRX.vKASOutgoing` → `EDWDM.TRX.vKasOutgoing`)

## Eklenen nesne (27)

- `EDWBridge.BDG.rpt_EDWCustomerProfitabilityBranchReport`
- `EDWDM.AIS.vCorporateAsset`
- `EDWDM.AIS.vCreditCardFPD`
- `EDWDM.CFM.vDigitalVehiclePayments`
- `EDWDM.CFM.vDigitalVehiclePaymentsBranchInfo`
- `EDWDM.CFM.vTotalVehiclePayments`
- `EDWDM.CMP.vCampaignEmail`
- `EDWDM.CMP.vCampaignPush`
- `EDWDM.CMP.vCampaignSMS`
- `EDWDM.CMP.vEmailMessage`
- `EDWDM.CMP.vNotificationCampaign`
- `EDWDM.CMP.vPushNotification`
- `EDWDM.CON.vCorporateParticipationDeposit`
- `EDWDM.CON.vIndividualCreditCardPortfolioSummary`
- `EDWDM.CON.vIndividualCreditCardTransactionSummary`
- `EDWDM.CON.vIndividualCustomerPortfolioSummary`
- `EDWDM.CON.vIndividualDebitCardApplicationSummary`
- `EDWDM.CON.vIndividualDebitCardCustomerPortfolioSummary`
- `EDWDM.CON.vIndividualDebitCardPortfolioSummary`
- `EDWDM.CON.vIndividualDebitCardTransactionSummary`
- `EDWDM.CRP.vAgricultureCustomerPeriod`
- `EDWDM.CRP.vCorporateCardData`
- `EDWDM.TRE.vTreasuryBehaviourLoyaltyFeatures`
- `EDWDM.TRE.vTreasuryBehaviourProductChannelFeatures`
- `EDWDM.TRE.vTreasuryBehaviourTransactionFeatures`
- `EDWDM.TRX.vBalanceChangeDetail`
- `EDWDM.TRX.vBalanceChangeDetailWeekly`

## Ambarda bulunmayan nesne (8)

- `EDWBridge.SME.rpt_EDWWorkingDepthSegmentation`
- `EDWBridge.TRX.rpt_EDWCallHoldDetailReport`
- `EDWDM.CMP.vCommunicationJournal`
- `EDWDM.CUS.vCustomerEfficiency`
- `EDWDM.CUS.vCustomerEfficiencyMonthly`
- `EDWDM.OTH.vApiHhsAccountConsent`
- `EDWDM.OTH.vAPIHhsAccountConsentRelation`
- `EDWDM.OTH.vAPIHhsAccountConsentUsage`

## Silinen kolon (79)

- `EDWDM.AIS.vCardLimitTable`: TotalCardLimit
- `EDWDM.BDG.vProductProfitabilityAccountsExternal`: SectorName
- `EDWDM.BDG.vProductProfitabilityAccountsInternal`: SectorName
- `EDWDM.CLS.vCollectionSolutionHGS`: CommissionAmount, CommissionDescription, CommissionId, CommissionJournalId, CommissionKey, CustomerName
- `EDWDM.CON.vCorporateInvestmentWakala`: DataDate, DepositDetail
- `EDWDM.CRP.vAgricultureCKS`: CurrentYearCKS, DefaultPersonId, PersonType
- `EDWDM.CRP.vAgricultureCustomer`: AncillaryProductUsageCount, CurrentYearCKS, DefaultPersonId, IsUME, MailPermissionFlag, MainProductUsageCount, MarketingActivityFlag, MobilActivityFlag, PushPermissionFlag, SegmentName, SMSPermissionFlag
- `EDWDM.CRP.vEExportProductUsage`: Deposit12MounthAvgAmount, Deposit3MounthAvgAmount, Deposit6MounthAvgAmount, TotalCurrentAmount, TotalDepositAmount, TotalParticipationAmount
- `EDWDM.CRP.vLeasingFundPayment`: Proje Tarihi, VendorId, VendorTitle
- `EDWDM.CRP.vLifePolicyList`: ChannelName, CreditFecName, InsuredBirthCityNo, LifePolicyNo, LifePolicyTypeIdName, PayerBirthCityNo, UpdateSystemDate
- `EDWDM.CRP.vTourismCustomer`: AncillaryProductUsageCount, Definition, DigitalSegment, MainPersonaFlag, MainProductUsageCount, MarketingActivityFlag, MobilActivity, PortfolioOwnerUserId, ReginalOfficeName, SubPersona1, SubPersona4, SubPersonaFlag
- `EDWDM.CUS.vAccountLastTransaction`: SystemDate, TranDate
- `EDWDM.DGM.vCustomerDailyLoginCounts`: CustomerPersonId
- `EDWDM.DGM.vCustomerPeriodicLoginCounts`: CustomerPersonId
- `EDWDM.FRG.vForeignTradeScenarioandLabel`: CreditRiskGroupNo, CustomerPartyNk
- `EDWDM.OTH.vOhvpsHhsAccountConsent`: AccountConsentId, AccountGroupId, OhvpsHhsAccountConsentNo
- `EDWDM.OTH.vOhvpsHhsPaymentConsent`: AccountConsentNk, AccountGroupNk, OhvpsHhsPaymentConsentNo
- `EDWDM.PRC.vArrayCashFinancing`: EstateMaxFundAmount
- `EDWDM.PRC.vCustomerGeneralInfo`: CCInstallementTranAvgAvgL12m, MaxOutgoingBankName, SystemDate
- `EDWDM.PTY.vCorporateDepositSegment`: EffectiveCurrent
- `EDWDM.TRE.vTreasuryValueFeatures`: EndDateOfThisTask, StartDateOfThisTask, SukukEfficiencyLast12Months, SukukEfficiencyLastYear, SukukEfficiencyThisYear, SystemDate, SystemUser
- `EDWDM.VCH.vValueChainTracking`: TotalEfficiency, TotalNonFundEfficiency

## Ambarda bulunmayan kolon (60)

- `EDWDM.AIS.vCardLimitTable`: TotalCardLimit
- `EDWDM.CFM.vDigitalVehiclePayments`: FundingFECNk
- `EDWDM.CFM.vDigitalVehiclePaymentsBranchInfo`: FundingFEC
- `EDWDM.CRP.vAgricultureCKS`: CultivatedArea, CurrentYearCKS, DefaultPersonId, PersonType
- `EDWDM.CRP.vAgricultureCustomer`: CurrentYearCKS, DefaultPersonId, IsUME
- `EDWDM.CRP.vAgricultureCustomerPeriod`: DefaultPersonId, IsSeedCardActive, IsSeedCardOpen
- `EDWDM.CRP.vLeasingFundPayment`: Proje Tarihi, VendorId, VendorTitle
- `EDWDM.CRP.vLifePolicyList`: ChannelName, CreditFecName, InsuredBirthCityNo, LifePolicyNo, LifePolicyTypeIdName, PayerBirthCityNo, UpdateSystemDate
- `EDWDM.CRP.vTourismCustomer`: AncillaryProductUsageCount, Definition, DigitalSegment, MainPersonaFlag, MainProductUsageCount, MarketingActivityFlag, MobilActivity, PortfolioOwnerUserId, ReginalOfficeName, SubPersona1, SubPersona4, SubPersonaFlag
- `EDWDM.CUS.vAccountLastTransaction`: SystemDate, TranDate
- `EDWDM.DGM.vCustomerDailyLoginCounts`: CustomerPersonId
- `EDWDM.DGM.vCustomerPeriodicLoginCounts`: CustomerPersonId
- `EDWDM.FRG.vForeignTradeScenarioandLabel`: CreditRiskGroupNo, CustomerPartyNk
- `EDWDM.OTH.vOhvpsHhsAccountConsent`: AccountConsentId, AccountGroupId, OhvpsHhsAccountConsentNo
- `EDWDM.OTH.vOhvpsHhsPaymentConsent`: AccountConsentNk, AccountGroupNk, OhvpsHhsPaymentConsentNo
- `EDWDM.PRC.vArrayCashFinancing`: EstateMaxFundAmount
- `EDWDM.PRC.vCustomerGeneralInfo`: SystemDate
- `EDWDM.PTY.vCorporateDepositSegment`: EffectiveCurrent
- `EDWDM.TRE.vTreasuryBehaviourLoyaltyFeatures`: SystemDate
- `EDWDM.TRE.vTreasuryValueFeatures`: EndDateOfThisTask, StartDateOfThisTask, SukukEfficiencyLast12Months, SukukEfficiencyLastYear, SukukEfficiencyThisYear, SystemDate, SystemUser
- `EDWDM.VCH.vValueChainTracking`: TotalEfficiency, TotalNonFundEfficiency

## EDWUTIL'de olmayıp korunan kolon (1)

- `EDWDM.CRP.vAgricultureCKS`: SumCultivatedArea

## Yazımı düzeltilen kolonlar (138)

Harf büyüklüğü dışındaki 20 düzeltme:

- `EDWDM.CON.vDebitCardMiles`: `RecordStatuName` → `RecordStatusName`
- `EDWDM.CRP.vAgricultureCKS`: `PersonnelFag` → `PersonnelFlag`
- `EDWDM.CRP.vCorporateCardData`: `Last3MothsSpendingAmountFlag` → `Last3MonthsSpendingAmountFlag`
- `EDWDM.CRP.vHealthPolicyList`: `ReginalOfficeId` → `RegionalOfficeId`
- `EDWDM.CRP.vHealthPolicyList`: `ReginalOfficeName` → `RegionalOfficeName`
- `EDWDM.CRP.vLeasingFutureCollection`: `ProjcetHistory` → `ProjectHistory`
- `EDWDM.CRP.vLifePolicyList`: `ReginalOfficeId` → `RegionalOfficeId`
- `EDWDM.CRP.vLifePolicyList`: `ReginalOfficeName` → `RegionalOfficeName`
- `EDWDM.CRP.vNeovaPolicyList`: `ReginalOfficeId` → `RegionalOfficeId`
- `EDWDM.CRP.vNeovaPolicyList`: `ReginalOfficeName` → `RegionalOfficeName`
- `EDWDM.CRP.vPolicyProductionDetail`: `ReginalOfficeId` → `RegionalOfficeId`
- `EDWDM.CRP.vPolicyProductionDetail`: `ReginalOfficeName` → `RegionalOfficeName`
- `EDWDM.CRP.vPrivatePension`: `ReginalOfficeId` → `RegionalOfficeId`
- `EDWDM.CRP.vPrivatePension`: `ReginalOfficeName` → `RegionalOfficeName`
- `EDWDM.CRP.vSupplierPurchaserInvoiceStatus`: `ReginalOfficeId` → `RegionalOfficeId`
- `EDWDM.CRP.vSupplierPurchaserInvoiceStatus`: `ReginalOfficeName` → `RegionalOfficeName`
- `EDWDM.CRP.vTourismCustomer`: `IDMScore` → `IDM_Score`
- `EDWDM.CRP.vTourismCustomer`: `KRIName` → `KRI_Name`
- `EDWDM.TRE.vTreasuryValueFeatures`: `RegionalOffice` → `ReginalOffice`
- `EDWDM.TRE.vTreasuryValueFeatures`: `RegionalOfficeName` → `ReginalOfficeName`

## Kişisel veri işareti temizliği (127 açıklama)

- `EDWBridge.CON.rpt_EDWDepositCustomer.CustomerName`: Müşterinin ad-soyad (gerçek kişi) veya ticari unvan (tüzel kişi) bilgisidir.
- `EDWBridge.CUS.rpt_EDWForeignCustomersBalanceReport.CustomerName`: Müşterinin ad-soyad (gerçek kişi) veya ticari unvan (tüzel kişi) bilgisidir.
- `EDWBridge.CUS.rpt_EDWForeignCustomersBalanceReport.DefaultEMail`: Müşterinin sistemde tanımlı birincil (varsayılan) e-posta adresidir. Bildirimler ve müşteri iletişiminde kull…
- `EDWBridge.CUS.rpt_EDWForeignCustomersBalanceReport.DefaultGSM`: Müşterinin sistemde tanımlı birincil (varsayılan) cep telefon numarasıdır. SMS/OTP ve müşteri iletişiminde ku…
- `EDWBridge.CUS.rpt_EDWPrivateBankingCustomerAssetChangeReport.CustomerName`: Müşterinin ad-soyad (gerçek kişi) veya ticari unvan (tüzel kişi) bilgisidir.
- `EDWBridge.CUS.rpt_EDWPrivateBankingCustomerReport.CitizenshipCountryName`: Müşterinin uyruğunun (vatandaşı olduğu ülkenin) okunabilir adıdır. Yabancı uyruklu müşterilerin ayrıştırılmas…

İş anlamı taşıdığı için dokunulmayan veya kalıba uymayan 11 metin kaldı:

- `vCustomerPermissions.ExplicitConsentPermissionKatılım`: Müşterinin Katılım bankacılığı ürün/hizmetlerine yönelik ticari elektronik ileti veya veri işleme amacıyla ve…
- `vMarketingCommunicationPermissions.MailPermission`: Müşterinin pazarlama/bilgilendirme amaçlı e-posta gönderimine izin verip vermediğini gösteren bayraktır (1: i…
- `vTourismCustomer.KTpermissionFlag`: Müşteriden kişisel verilerin işlenmesine ilişkin açık rıza beyan formunun alınıp alınmadığını gösteren bayrak…
- `vCustomerInfo.CustomerConfidentialInfoFlag`: Müşterinin kişisel/finansal bilgilerinin üçüncü taraflarla veya grup şirketleriyle paylaşımına izin verip ver…
- `vCustomerInfo.SensitiveInformationPermissionFlag`: Müşterinin özel nitelikli (hassas) kişisel verilerinin işlenmesine ilişkin iznini gösteren bayraktır. KVKK ka…
- `vKASIncoming.PaymentIdentityNumber`: Ödemeyi gerçekleştiren kişinin kimlik numarasıdır (T.C. Kimlik No veya yabancı kimlik no). Kişisel veri nitel…
- `vKASIncoming.PaymentName`: Ödemeyi gerçekleştiren kişinin ad-soyad bilgisidir. Kişisel veri niteliğinde olup işlem tarafının tanımlanmas…
- `vKASIncoming.PaymentPhoneNumber`: Ödemeyi gerçekleştiren kişinin telefon numarasıdır. İletişim ve doğrulama amacıyla kullanılan kişisel veridir.
- `vKASIncoming.ReceiverPassportNumber`: Parayı alacak kişinin (alıcının) pasaport numarasıdır. Yabancı uyruklu alıcılarda kimlik doğrulama amacıyla T…
- `vKASIncoming.ReceiverPhoneNumber`: Parayı alacak kişinin (alıcının) telefon numarasıdır. İletişim ve kimlik doğrulama amacıyla kullanılan kişise…
- `vKASIncoming.SenderPhoneNumber`: Parayı gönderen kişinin telefon numarasıdır. İletişim ve kimlik doğrulama amacıyla kullanılan kişisel veridir.

## Hedef biçime getirilen yeni açıklamalar (739)

| Nesne | Kolon | Eski | Yeni |
|---|---|---|---|
| rpt_EDWCustomerProfitabilityBranchReport |  | Şube Bazlı Karlılık Listeleme raporu. Genel müdürlük,bilge ve şube se… | Şube Bazlı Karlılık Listeleme raporu. Genel müdürlük, bilge ve şube seviyesinde yetkilendirmelere uygun şekil… |
| rpt_EDWCustomerProfitabilityBranchReport | AccountNumber | Müşteri No | Müşteri No. |
| rpt_EDWCustomerProfitabilityBranchReport | AccountSuffix | Ek No | Ek No. |
| rpt_EDWCustomerProfitabilityBranchReport | BranchName | Şube | Şube Adı. |
| rpt_EDWCustomerProfitabilityBranchReport | CreditRiskGroupName | Finansman Risk Grup Adı | Finansman Risk Grup Adı. |
| rpt_EDWCustomerProfitabilityBranchReport | CreditRiskGroupNo | Finansman Risk Grup No | Finansman Risk Grup No. |
| rpt_EDWCustomerProfitabilityBranchReport | CustomerName | Müşteri Adı | Müşteri Adı. |
| rpt_EDWCustomerProfitabilityBranchReport | ExpenseAmount | Gider | Gider. |
| rpt_EDWCustomerProfitabilityBranchReport | FECName | Döviz Adı | Döviz Adı. |
| rpt_EDWCustomerProfitabilityBranchReport | IncomeAmount | Gelir | Gelir. |
| rpt_EDWCustomerProfitabilityBranchReport | ItemName | Kalem Adı | Kalem Adı. |
| rpt_EDWCustomerProfitabilityBranchReport | NetProfitabilityAmount | Net Kar | Net Kar. |
| rpt_EDWCustomerProfitabilityBranchReport | ProductName | Ürün Adı,Karlılık ağaç yapısındaki son kırılımdaki veriyi gösterir | Ürün Adı, Karlılık ağaç yapısındaki son kırılımdaki veriyi gösterir. |
| rpt_EDWCustomerProfitabilityBranchReport | ProfitabilityProductCode | Ürün Grubu, Karlılık ağaç yapısındaki ilk kırılımdaki veriyi gösterir | Ürün Grubu, Karlılık ağaç yapısındaki ilk kırılımdaki veriyi gösterir. |
| rpt_EDWCustomerProfitabilityBranchReport | ProfitabilityProductSubCode | Ürün Alt Grubu,Karlılık ağaç yapısındaki ilk kırılımdaki veriyi göste… | Ürün Alt Grubu, Karlılık ağaç yapısındaki ilk kırılımdaki veriyi gösterir. |
| rpt_EDWCustomerProfitabilityBranchReport | RegionName | Bölge | Bölge. |
| rpt_EDWCustomerProfitabilityBranchReport | SectorName | Sektör Adı | Sektör Adı. |
| vCorporateAsset |  | Mevduat ürün bilgileri kapanan aylar için alınmaktadır. | Mevduat ürünleri için kapanan aylara ait varlık ve risk bilgilerini içeren kurumsal varlık tablosu. |
| vCorporateAsset | AssetsToCashRisk | Müşterinin o periyottaki toplam varlık bakiyesinin (katılım +cari +ya… | Müşterinin o periyottaki toplam varlık bakiyesinin (katılım + cari + yatırım fonu + sukuk) nakdi riske bölünm… |
| vCorporateAsset | BranchName | Şube ismidir. | Şube ismi. |
| vCorporateAsset | CashRisk | Müşterinin o periyottaki makdi risk bakiyesini(AmountLC) verir. | Müşterinin o periyottaki nakdi risk bakiyesini (AmountLC) verir. |
| vCorporateAsset | CustomerClassName | Müşteri sınıf ismidir. | Müşteri sınıf ismi. |
| vCorporateAsset | CustomerId | Müşteri numarasıdır. | Müşteri numarası. |
| vCorporateAsset | CustomerName | Müşteri ismidir. | Müşteri ismi. |
| vCorporateAsset | CustomerPartyId | müşteri numarası | Müşteri numarası. |
| vCorporateAsset | CustomerRiskGroup | Müşterinin risk grubu bilgisini verir. Customer tablosundaki Customer… | Müşterinin risk grubu bilgisi. |
| vCorporateAsset | CustomerTypeDetail | Müşterinin Tüzel, gk ya da sahıs firması olup olmadıgı bilgisini verir | Müşterinin Tüzel, GK ya da şahıs firması olup olmadığı bilgisi. |
| vCorporateAsset | DepositsToCashRisk | Müşterinin o periyottaki toplam mevduatının (katılım +cari ) nakdi ri… | Müşterinin o periyottaki toplam mevduatının (katılım + cari) nakdi riske bölünmesi ile oluşan rasyodur. |
| vCorporateAsset | Period | Periyot | Periyot. |
| vCorporateAsset | PersonnelFlag | personel bayragı | Personel bayrağı. |
| vCorporateAsset | PortfolioOwnerName | Portföy Temsilcisi | Portföy Temsilcisi. |
| vCorporateAsset | ReginalOfficeName | Bölge müdürlüğü ismidir. | Bölge müdürlüğü ismi. |
| vCorporateAsset | RiskGroupAverageCurrentAccount | Risk grubunun o periyottaki toplam cari ortalamasını (MeanAmountLc) v… | Risk grubunun o periyottaki toplam cari ortalamasını (MeanAmountLc) verir. |
| vCorporateAsset | RiskGroupAverageDepositAccount | Risk grubunun o periyottaki toplam katılım ortalamasını (MeanAmountLc… | Risk grubunun o periyottaki toplam katılım ortalamasını (MeanAmountLc) verir. |
| vCorporateAsset | RiskGroupAverageInvestmentFund | Risk grubunun o periyottaki toplam yatırım fonu ortalamasını(AmountLc… | Risk grubunun o periyottaki toplam yatırım fonu ortalamasını (AmountLc) verir. |
| vCorporateAsset | RiskGroupAverageSukuk | Risk grubunun o periyottaki toplam sukuk ortalamasını (AmountLc) veri… | Risk grubunun o periyottaki toplam sukuk ortalamasını (AmountLc) verir. |
| vCorporateAsset | RiskGroupCurrentAccount | Risk grubunun o periyottaki toplam cari bakiyesini(AmountLc) verir. | Risk grubunun o periyottaki toplam cari bakiyesini (AmountLc) verir. |
| vCorporateAsset | RiskGroupDepositAccount | Risk grubunun o periyottaki toplam katılım bakiyesini (AmountLc) veri… | Risk grubunun o periyottaki toplam katılma bakiyesini (AmountLc) verir. |
| vCorporateAsset | RiskGroupInvestmentFund | Risk grubunun o periyottaki toplam yatırım fonu bakiyesini (AmountLc)… | Risk grubunun o periyottaki toplam yatırım fonu bakiyesini (AmountLc) verir. |
| vCorporateAsset | RiskGroupSukuk | Risk grubunun o periyottaki toplam sukuk bakiyesini (AmountLc) verir. | Risk grubunun o periyottaki toplam sukuk bakiyesini (AmountLc) verir. |

## Modelin tutarsız bulduğu kaynak açıklamaları (0)


## Uyarılar (9, saklanan ilk 9)

- ERPDM değerlendirilmedi; mevcut kayıtları korundu.
- 107 kaynak satırı bozuk veya yinelenen olduğu için atlandı.
- EDWDM.AIS.vCorporateAsset: modelin 8 değeri kurala uymadığı için alınmadı.
- EDWDM.AIS.vCorporateAsset: modelin 1 değeri kurala uymadığı için alınmadı.
- EDWDM.AIS.vCreditCardFPD: modelin 4 değeri kurala uymadığı için alınmadı.
- EDWDM.AIS.vCreditCardFPD: modelin 2 değeri kurala uymadığı için alınmadı.
- EDWDM.CON.vIndividualCustomerPortfolioSummary: modelin 1 değeri kurala uymadığı için alınmadı.
- EDWDM.CRP.vAgricultureCustomer: modelin 3 değeri kurala uymadığı için alınmadı.
- EDWDM.CRP.vAgricultureCustomerPeriod: modelin 7 değeri kurala uymadığı için alınmadı.

## Tutarlılık taraması (değiştirilmedi, inceleme adayı)

Kurala dayalı kaba taramadır; yanlış alarm içerir, tutarsızlığın tamamını bulmaz.

- Adla uyuşmayan aday: **367**
- 20 karakterden kısa açıklama: **244**
- Boş açıklama: **0**

| Neden | Adet |
|---|---:|
| Adet kolonu, açıklamada karşılığı yok | 179 |
| Ad kolonu, açıklamada karşılığı yok | 59 |
| Numara kolonu, açıklamada karşılığı yok | 56 |
| Bayrak kolonu, açıklamada karşılığı yok | 48 |
| Ad kolonu, açıklaması başka kavram anlatıyor | 11 |
| Tarih kolonu, açıklamada karşılığı yok | 7 |
| Adet kolonu, açıklaması başka kavram anlatıyor | 5 |
| Numara kolonu, açıklaması başka kavram anlatıyor | 2 |

| Nesne | Kolon | Neden | Açıklama |
|---|---|---|---|
| rpt_EDWALCOCreditProjectDetail | EWSCustomerColorName | Ad kolonu, açıklaması başka kavram anlatıyor | Müşterinin Erken Uyarı Sistemi (Early Warning System — EWS) çıktısına göre atanan renk kodudur (gen… |
| vCustomerProjectDetail | EWSCustomerColorName | Ad kolonu, açıklaması başka kavram anlatıyor | Müşteriye ait Erken Uyarı Sistemi (EWS) risk renk kodunu gösterir (ör. yeşil, sarı, kırmızı); müşte… |
| vCustomerProjectDetail | EWSGroupColorName | Ad kolonu, açıklaması başka kavram anlatıyor | Müşterinin bağlı olduğu risk/şirketler grubuna ait Erken Uyarı Sistemi (EWS) renk kodunu gösterir. … |
| vCampaign | CampaignDetailUpdateUserName | Ad kolonu, açıklaması başka kavram anlatıyor | Kampanya detay kaydını son güncelleyen kullanıcının kodudur (Kullanıcı Kodu); denetim izi (audit tr… |
| vCampaign | CampaignUserName | Ad kolonu, açıklaması başka kavram anlatıyor | Kampanya kaydını oluşturan/işleyen kullanıcının çekirdek bankacılık sistemindeki kullanıcı kodudur … |
| vEcommerceRefund | CompanyId | Numara kolonu, açıklaması başka kavram anlatıyor | Şirketi tanımlayan alandır (Şirket Adı). E-ticaret iade işleminin ait olduğu şirketin belirlenmesin… |
| vEcommerceSmsTransaction | CompanyId | Numara kolonu, açıklaması başka kavram anlatıyor | E-ticaret SMS doğrulama işleminin ilişkili olduğu üye işyerini/şirketi tanımlayan alandır (Şirket A… |
| vCollateral | CollateralStateName | Ad kolonu, açıklaması başka kavram anlatıyor | Teminat durum kodunun (CollateralStateId) okunabilir karşılığıdır. |
| vActualBrief | BudgetReportName | Ad kolonu, açıklaması başka kavram anlatıyor | Bütçe rapor kaleminin bağlı olduğu bütçe grubunu/kodunu ifade eder. Bütçe raporlaması ve kalem sını… |
| vActualDistribution | BudgetReportName | Ad kolonu, açıklaması başka kavram anlatıyor | Dağıtım kaydının ilişkili olduğu bütçe raporunun numarasıdır (Rapor No). |
| vLifePolicyList | PayerIncomeRangeName | Ad kolonu, açıklaması başka kavram anlatıyor | Poliçe primini ödeyen kişinin gelir aralığı kodunun okunabilir karşılığıdır. |
| vPRCArrayPOS | EarlyReleaseTransactionCount | Adet kolonu, açıklaması başka kavram anlatıyor | Müşterinin, provizyonda bekleyen POS tahsilat tutarından komisyon ödeyerek erken tahsilat yoluyla c… |
| vPRCProjectReceivableInfo | EarlyCollectedInstallmentCount | Adet kolonu, açıklaması başka kavram anlatıyor | Müşterinin tüm nakdi fon kullandırımlarında ödediği taksitlerden, son ödeme tarihinden önce (erken)… |
| vOhvpsHhsPaymentConsent | KolasAccountTypeName | Ad kolonu, açıklaması başka kavram anlatıyor | Kolas sorgusu sonucunda dönen hesabın bireysel mi kurumsal mı olduğunu belirten okunabilir alandır.… |
| vFirmAndShareholdersDepositAnalysis | FirmCurrentActiveProductCount | Adet kolonu, açıklaması başka kavram anlatıyor | Firmanın güncel (rapor tarihindeki) aktif olarak kullandığı bankacılık ürünü adedidir. Ortalama değ… |
| vFirmAndShareholdersDepositAnalysis | SHCurrentActiveProductCount | Adet kolonu, açıklaması başka kavram anlatıyor | Firma ortağının güncel (rapor tarihindeki) aktif olarak kullandığı bankacılık ürünü adedidir. |
| vCustomerMoneyTransferSummary | FASTIncomingCount | Adet kolonu, açıklaması başka kavram anlatıyor | Müşterinin ilgili dönemde FAST sistemi üzerinden hesabına gelen para transferi işlem adedidir. Döne… |
| vIntrabankMoneyTransfer | QRCodeFlowTypeName | Ad kolonu, açıklaması başka kavram anlatıyor | Para transferinin QR kod (karekod) üzerinden gerçekleştirildiği akış tipini gösteren okunabilir ala… |
| rpt_EDWCorporateProductSegmentationCustomerInput | InvestmentAccountsuffixCount | Adet kolonu, açıklamada karşılığı yok | Müşterinin son 2 sene içerisinde işlem gördüğü farklı yatırım hesap suffix adedidir. Hesap suffix'i… |
| rpt_EDWCorporateProductSegmentationCustomerInput | InvestmentFlag | Bayrak kolonu, açıklamada karşılığı yok | Müşterinin yatırım ürünleri ve pozisyon riskleri üzerinden hesaplanan yatırımcı etiketi bayrağıdır … |
| rpt_EDWCorporateProductSegmentationCustomerInput | InvestmentFundCount | Adet kolonu, açıklamada karşılığı yok | Müşterinin son 2 sene içerisinde işlem gördüğü farklı yatırım fonu kodu adedidir. Yatırım fonu port… |
| rpt_EDWCorporateProductSegmentationCustomerInput | SukukISINCount | Adet kolonu, açıklamada karşılığı yok | Müşterinin son 2 sene içerisinde işlem gördüğü farklı sukuk ISIN kodu adedidir. Sukuk (kira sertifi… |
| rpt_EDWCorporateProductSegmentationCustomerInput | SukukVarietyCount | Adet kolonu, açıklamada karşılığı yok | Müşterinin son 2 sene içerisinde işlem gördüğü farklı sukuk (kira sertifikası) adedidir. SukukISINC… |
| rpt_EDWCustomerProfitabilityBranchReport | RegionName | Ad kolonu, açıklamada karşılığı yok | Bölge. |
| rpt_EDWDepositCustomer | AccomodationName | Ad kolonu, açıklamada karşılığı yok | Müşterinin yerleşim yerinin yurt içi mi yurt dışı mı olduğunu gösteren metin bilgisi (Yurt İçi / Yu… |
| rpt_EDWDepositCustomer | CitizenshipCountryName | Ad kolonu, açıklamada karşılığı yok | Müşterinin uyruğunu (vatandaşlık ülkesini) gösteren metin bilgisidir. AML/regulatory analizde ulusl… |
| rpt_EDWDepositCustomer | CitizenshipName | Ad kolonu, açıklamada karşılığı yok | Müşterinin yerli/yabancı ayrımını gösteren metin bilgisi (Yerli / Yabancı). CitizenshipCountryName'… |
| rpt_EDWDepositCustomerAssetInfoDashboard | DepositCustomerFlag | Bayrak kolonu, açıklamada karşılığı yok | Müşterinin cari ürünlerindeki bakiyenin belirlenen baz tutar eşiğinin üzerinde olması halinde konul… |
| rpt_EDWForeignCustomersBalanceReport | CitizenshipCountryName | Ad kolonu, açıklamada karşılığı yok | Müşterinin uyruğunu (vatandaşlık ülkesini) gösteren metin bilgisidir. Yabancı müşteri raporunda ulu… |
| rpt_EDWForeignCustomersBalanceReport | GenderName | Ad kolonu, açıklamada karşılığı yok | Gerçek kişi müşterinin cinsiyet bilgisidir (Erkek / Kadın). Demografik segmentasyonda kullanılır. |
| rpt_EDWForeignCustomersBalanceReport | MaritalStatusName | Ad kolonu, açıklamada karşılığı yok | Müşterinin medeni durum bilgisidir (Evli / Bekar / Dul / Boşanmış). |
| rpt_EDWPrivateBankingCustomerAssetChangeReport | AccomodationName | Ad kolonu, açıklamada karşılığı yok | Müşterinin ikamet ettiği yerleşim yerini (il/ilçe veya bölge) gösterir. Özel bankacılık portföy yön… |
| rpt_EDWPrivateBankingCustomerAssetChangeReport | CitizenshipCountryName | Ad kolonu, açıklamada karşılığı yok | Müşterinin uyruk bilgisini (vatandaşı olduğu ülke) gösterir. Özel bankacılık müşteri profilinde KYC… |
| rpt_EDWALCOCreditProjectDetail | AllotmentStatusName | Ad kolonu, açıklamada karşılığı yok | Kredi/finansman tahsisinin güncel durumudur (ör. Onay Bekliyor, Onaylandı, Reddedildi, Kullanıldı, … |
| rpt_EDWALCOCreditProjectDetail | LoanTypeName | Ad kolonu, açıklamada karşılığı yok | Fon kullandırımın (kredinin) tipini gösterir (ör. Nakit / Gayri Nakdi, Kısa/Orta/Uzun Vadeli, Rotat… |
| rpt_EDWGenesysNumericalValues | AverageWrapUpTime | Tarih kolonu, açıklamada karşılığı yok | Çağrı bitiminden sonra temsilcinin çağrı kayıtlarını tamamlaması için harcadığı ortalama süredir (a… |
| rpt_EDWGenesysNumericalValues | StaffTime | Tarih kolonu, açıklamada karşılığı yok | Temsilcinin sistemde aktif oturum açık olduğu (çalışma) süresidir. Verimlilik hesabında payda olara… |
| rpt_EDWMerchantEODReport | TransactionCount | Adet kolonu, açıklamada karşılığı yok | Rapor kırılımındaki toplam işlem adedidir. |
| rpt_EDWMerchantPOSSetupOrderReport | InsertUserPartyId | Numara kolonu, açıklamada karşılığı yok | Kaydı oluşturan kullanıcının sistem kimliğidir (SKEY). |
| rpt_EDWMerchantTransactionDetailReport | MerchantBlockPeriodId | Numara kolonu, açıklamada karşılığı yok | Bloke işleminin ait olduğu periyodun (genellikle YYYYMM formatında) kimliğidir. Bloke tutarlarının … |
| vCardFirstTransaction | First30DayTrnCount | Adet kolonu, açıklamada karşılığı yok | Müşterinin kartını ilk kullanmaya başladığı ilk 30 işlem günü içerisinde gerçekleştirdiği toplam iş… |
| vCardFirstTransaction | FirstDayTrnCount | Adet kolonu, açıklamada karşılığı yok | Müşterinin kartını ilk kullandığı işlem gününde gerçekleştirdiği toplam işlem adedini gösterir. Kar… |
| vCardLimitTable | TotalCount | Adet kolonu, açıklamada karşılığı yok | Müşterinin son 3 yıl içerisindeki toplam kart harcama işlem adedidir. Kart kullanım yoğunluğu ve mü… |
| vCardMonthlyTransaction | TransactionCount | Adet kolonu, açıklamada karşılığı yok | Müşterinin ilgili ayda kartla gerçekleştirdiği toplam işlem adedidir. Kart kullanım yoğunluğu ve ak… |
| vCardWeeklyTransaction | TransactionCount | Adet kolonu, açıklamada karşılığı yok | Müşterinin ilgili ay içerisinde kartla gerçekleştirdiği toplam işlem adedini gösterir. Aylık işlem … |
| vCorporateAsset | BranchName | Ad kolonu, açıklamada karşılığı yok | Şube ismi. |
| vCorporateAsset | CustomerClassName | Ad kolonu, açıklamada karşılığı yok | Müşteri sınıf ismi. |
| vCorporateAsset | CustomerName | Ad kolonu, açıklamada karşılığı yok | Müşteri ismi. |
| vCorporateAsset | PersonnelFlag | Bayrak kolonu, açıklamada karşılığı yok | Personel bayrağı. |
| vCorporateAsset | PortfolioOwnerName | Ad kolonu, açıklamada karşılığı yok | Portföy Temsilcisi. |
| vCorporateAsset | ReginalOfficeName | Ad kolonu, açıklamada karşılığı yok | Bölge müdürlüğü ismi. |
| vCreditCardFPD | AppChannelId | Numara kolonu, açıklamada karşılığı yok | Başvuru kanalı kimliği. |
| vCreditCardFPD | ApplicationWfStatusName | Ad kolonu, açıklamada karşılığı yok | Başvuru durumu. |
| vCreditCardFPD | DigitalRecordFlag | Bayrak kolonu, açıklamada karşılığı yok | Dijital kullanımı Var/Yok |
| vCreditCardFPD | FirmSalaryFlag | Bayrak kolonu, açıklamada karşılığı yok | Müşterinin Maaş müşterisi olup olmadığı bilgisi. |
| vCreditCardFPD | IncomeDeclaredMaxL3MDate | Tarih kolonu, açıklamada karşılığı yok | Son 3 aydaki tüm başvurularında beyan edilen max gelir bilgisin date bilgisi (kredi ve limit değişi… |
| vCreditCardFPD | IncomeDeclaredMaxL6MDate | Tarih kolonu, açıklamada karşılığı yok | Son 6 aydaki tüm başvurularında beyan edilen max gelir bilgisin date bilgisi (kredi ve limit değişi… |
| vCreditCardFPD | IncomeDeclaredMinL3MDate | Tarih kolonu, açıklamada karşılığı yok | Son 3 aydaki tüm başvurularında beyan edilen min gelir bilgisin date bilgisi (kredi ve limit değişi… |
| vCreditCardFPD | IncomeDeclaredMinL6MDate | Tarih kolonu, açıklamada karşılığı yok | Son 6 aydaki tüm başvurularında beyan edilen min gelir bilgisin date bilgisi (kredi ve limit değişi… |
| vCreditCardFPD | KKBCardCount | Adet kolonu, açıklamada karşılığı yok | KKB kapsamında kullanılan kredi kartlarının adedi. |
| vCreditCardFPD | KKBCreditCount | Adet kolonu, açıklamada karşılığı yok | KKB kapsamında kullanılan bireysel kredilerin ve kredili mevduat hesaplarının adedi. |
| vCreditCardFPD | KKBMortgageCreditCount | Adet kolonu, açıklamada karşılığı yok | KKB kapsamında kullanılan konut kredilerinin adedi. |
| vCreditCardFPD | MobilChannelFlag | Bayrak kolonu, açıklamada karşılığı yok | Mobil kanal kullanımı Var/Yok. |
| vCreditCardFPD | MultiProductApplyFlag | Bayrak kolonu, açıklamada karşılığı yok | Müşterinin başvuru yaptığı gün yapmış olduğu kredi, limit değişim ve kredi kartı başvuru sayısı. |
| vCreditCardFPD | OutgoingBankCount | Adet kolonu, açıklamada karşılığı yok | Son 1 yılda eftelere konu banka bilgisi. |
| vCreditCardFPD | PersonnelFlag | Bayrak kolonu, açıklamada karşılığı yok | Personel bayrağı. |
| vCreditCardFPD | ResidenceCityName | Ad kolonu, açıklamada karşılığı yok | Müşteri başvuru tarihindeki ikametgah şehir bilgisi. |
| vCreditCardFPD | TaxNumber | Numara kolonu, açıklamada karşılığı yok | TCKN. |
| vCrossSellTrainingInput | AutoLoanUsedFlag | Bayrak kolonu, açıklamada karşılığı yok | Müşterinin, eğitim döneminin 1 ay öncesindeki periyotta taşıt finansmanı (araç kredisi) ürününe sah… |
| vCrossSellTrainingInput | BESUsedFlag | Bayrak kolonu, açıklamada karşılığı yok | Müşterinin, eğitim döneminin 1 ay öncesindeki periyotta Bireysel Emeklilik Sistemi (BES) ürününe sa… |
| vCrossSellTrainingInput | CarInsuranceUsedFlag | Bayrak kolonu, açıklamada karşılığı yok | Müşterinin, eğitim döneminin 1 ay öncesindeki periyotta araç sigortası ürününe sahip ve aktif bir m… |
| vCrossSellTrainingInput | CreditCardUsedFlag | Bayrak kolonu, açıklamada karşılığı yok | Müşterinin, eğitim döneminin 1 ay öncesindeki periyotta kredi kartı ürününe sahip ve aktif bir müşt… |
| vCrossSellTrainingInput | CurrentDollarUsedFlag | Bayrak kolonu, açıklamada karşılığı yok | Müşterinin, eğitim dönemi başında cari dolar hesabı ürününe sahip ve aktif bir müşteri olup olmadığ… |
| vCrossSellTrainingInput | CurrentEuroUsedFlag | Bayrak kolonu, açıklamada karşılığı yok | Müşterinin, eğitim dönemi başında cari euro hesabı ürününe sahip ve aktif bir müşteri olup olmadığı… |
| vCrossSellTrainingInput | CurrentGoldUsedFlag | Bayrak kolonu, açıklamada karşılığı yok | Müşterinin, eğitim dönemi başında cari altın hesabı ürününe sahip ve aktif bir müşteri olup olmadığ… |
| vCrossSellTrainingInput | CurrentOtherFXUsedFlag | Bayrak kolonu, açıklamada karşılığı yok | Müşterinin, eğitim dönemi başında cari diğer döviz (dolar ve euro hariç) hesabı ürününe sahip ve ak… |
| vCrossSellTrainingInput | CurrentOtherPMUsedFlag | Bayrak kolonu, açıklamada karşılığı yok | Müşterinin, eğitim dönemi başında cari diğer kıymetli maden (altın ve gümüş hariç) hesabı ürününe s… |
| vCrossSellTrainingInput | CurrentSilverUsedFlag | Bayrak kolonu, açıklamada karşılığı yok | Müşterinin, eğitim dönemi başında cari gümüş hesabı ürününe sahip ve aktif bir müşteri olup olmadığ… |
| vCrossSellTrainingInput | DebitCardShopUsedFlag | Bayrak kolonu, açıklamada karşılığı yok | Müşterinin, eğitim döneminin 1 ay öncesindeki periyotta banka/debit kart ile alışveriş ürününe sahi… |
| vCrossSellTrainingInput | DepositDollarUsedFlag | Bayrak kolonu, açıklamada karşılığı yok | Müşterinin, eğitim dönemi başında katılım dolar hesabı ürününe sahip ve aktif bir müşteri olup olma… |

## Terim ve durak kelime önerileri (147, onay bekliyor)

- stopword: `Active` 
- stopword: `Activity` 
- stopword: `Address` 
- stopword: `Advance` 
- stopword: `Agriculture` 
- stopword: `App` 
- stopword: `Application` 
- stopword: `Authorization` 
- stopword: `Average` 
- stopword: `Avg` 
- stopword: `Bank` 
- stopword: `Behaviour` 
- stopword: `Business` 
- stopword: `Campaign` 
- stopword: `Cancel` 
- stopword: `Car` 
- stopword: `Change` 
- stopword: `CKS` 
- stopword: `Class` 
- stopword: `Code` 
- stopword: `Collection` 
- stopword: `Commerce` 
- stopword: `Company` 
- stopword: `Consent` 
- stopword: `Corporate` 
- stopword: `Correspond` 
- stopword: `Cost` 
- stopword: `Curr` 
- stopword: `Current` 
- stopword: `Data` 
- stopword: `Date` 
- stopword: `Day` 
- stopword: `Debit` 
- stopword: `Declared` 
- stopword: `Default` 
- stopword: `Demand` 
- stopword: `Detail` 
- stopword: `Digital` 
- stopword: `Efficiency` 
- stopword: `Email` 
- stopword: `End` 
- stopword: `Export` 
- stopword: `FEC` 
- stopword: `Flag` 
- stopword: `Foreign` 
- stopword: `Forward` 
- stopword: `Frequency` 
- stopword: `Funding` 
- stopword: `FXPMF` 
- stopword: `Group` 
- stopword: `GSM` 
- stopword: `Has` 
- stopword: `Health` 
- stopword: `Identity` 
- stopword: `Import` 
- stopword: `Installment` 
- stopword: `Insured` 
- stopword: `Inv` 
- stopword: `Investment` 
- stopword: `KRI` 
