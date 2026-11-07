"""Following a column through view and procedure code (011-dictionary-sync)."""

from app.infrastructure.dictionary_source.lineage import (
    KIND_LOGIC,
    KIND_PLAIN,
    Code,
    clean_sql,
    column_evidence,
    object_scope,
    parse_query,
    select_item,
    split_top,
)

VIEW = """/* Created by someone 01.01.2026 */
CREATE VIEW [CMP].[vPush]
AS
SELECT p.PushNk AS PushId
,p.CampaignNk AS CampaignId
,nc.NotificationCampaignNk AS NotificationCampaignId
,p.RetryCount
,(CASE WHEN L.PartyId IS NOT NULL THEN 1 ELSE 0 END) AS PersonnelFlag
FROM EDW.CMP.Push p WITH (NOLOCK)
LEFT JOIN EDW.CMP.NotificationCampaign nc WITH (NOLOCK) ON p.NotificationCampaignId = nc.NotificationCampaignId
AND GETDATE() BETWEEN nc.EdwValidFrom AND nc.EdwValidUntil
LEFT JOIN EDWUTIL.DTG.LKPParty AS L ON p.PartyId = L.PartyId
WHERE GETDATE() BETWEEN p.EdwValidFrom AND p.EdwValidUntil AND p.SystemDate >= '2025-01-01'
"""

LOAD = """CREATE PROCEDURE [CMP].[ins_Push](@EdwLoadId INT) AS BEGIN
TRUNCATE TABLE EDWLRY.CMP.Push;
INSERT INTO EDWLRY.CMP.Push (PushId, PushNk, NotificationCampaignId, CampaignNk, RetryCount)
SELECT DISTINCT CPK.PushId AS PushId, STG.PushId PushNk,
--CASE WHEN STG.CampaignId = 5 THEN 99 END Old,
CASE WHEN STG.CampaignId > 0 THEN NCK.NotificationCampaignId ELSE NULL END AS NotificationCampaignId,
STG.CampaignId AS CampaignNk,
STG.RetryCount
FROM EDWSTG.BOAINF.CAM_Push AS STG
INNER JOIN EDWSKEY.CMP.PushKey CPK ON STG.PushId = CPK.PushNk;
END;"""

CTE_VIEW = """CREATE VIEW [CMP].[vCover] AS
WITH Total AS (
SELECT C.PartyId, SUM(CASE WHEN SendDate >= DATEADD(DAY,-15,GETDATE()) THEN 1 ELSE 0 END) Total15
FROM EDW.CMP.Push P
INNER JOIN EDW.CMP.LKPStatus S ON P.StatusId = S.StatusId AND S.StatusNk IN ('6','10')
WHERE SendDate >= DATEADD(YEAR,-2,GETDATE())
GROUP BY C.PartyId
)
SELECT T.PartyId, CASE WHEN Total15 > 0 THEN 1 ELSE 0 END Cover15, Total15 FROM Total AS T
"""

TEMP_PROC = """CREATE PROCEDURE [TRE].[ins_Behaviour] AS BEGIN
SELECT a.PartyId, 9 DefinitionId INTO #Leaving FROM EDW.TRE.Deal a;
INSERT INTO [EDWDM].[TRE].[Behaviour] (PartyId, DefinitionId, BehaviourValue)
SELECT CL.PartyId, CL.DefinitionId, 1 AS BehaviourValue FROM (SELECT PartyId, DefinitionId FROM #Leaving) CL;
END"""


def code() -> Code:
    return Code.build(
        {
            "EDWDM.CMP.vPush": VIEW,
            "EDWLRY.CMP.ins_Push": LOAD,
            "EDWDM.CMP.vCover": CTE_VIEW,
            "EDWDM.TRE.ins_Behaviour": TEMP_PROC,
            "EDWDM.TRE.vBehaviour": "CREATE VIEW TRE.vBehaviour AS SELECT T1.BehaviourValue FROM [EDWDM].[TRE].[Behaviour] T1",
        }
    )


def test_commented_out_code_and_authors_leave_but_rule_comments_stay() -> None:
    text = clean_sql(
        "-- created by x\n--CASE WHEN a=1 THEN 2 END\nSELECT 1 -- son 3 aylık oran\n"
    )
    assert "CASE" not in text
    assert "created" not in text
    assert "son 3 aylık oran" in text


def test_select_items_read_every_alias_form() -> None:
    assert select_item("p.PushNk AS PushId") == ("PushId", "p.PushNk")
    assert select_item("STG.PushId PushNk") == ("PushNk", "STG.PushId")
    assert select_item("Total = a + b") == ("Total", "a + b")
    assert select_item("p.RetryCount") == ("RetryCount", "p.RetryCount")
    assert select_item("CASE WHEN a=1 THEN 1 ELSE 0 END Flag")[0] == "Flag"


def test_commas_inside_functions_do_not_split() -> None:
    assert split_top("a, ISNULL(b, 0) c, CASE WHEN x IN (1,2) THEN 1 END d") == [
        "a",
        "ISNULL(b, 0) c",
        "CASE WHEN x IN (1,2) THEN 1 END d",
    ]


def test_a_query_knows_its_sources_joins_and_filter() -> None:
    query = parse_query(VIEW.split("AS\n", 1)[1])
    assert query.sources["p"] == "edw.cmp.push"
    assert query.sources["nc"] == "edw.cmp.notificationcampaign"
    assert "SystemDate" in query.where


def test_a_column_reaches_the_load_procedure_with_only_its_own_logic() -> None:
    found = column_evidence(code(), "EDWDM.CMP.vPush", "NotificationCampaignId")
    text = " ".join(found.steps)
    assert found.kind == KIND_LOGIC
    assert "STG.CampaignId > 0" in text
    assert "THEN 99" not in text
    assert "PersonnelFlag" not in text


def test_a_renamed_column_keeps_its_source_and_never_borrows_a_neighbour() -> None:
    text = " ".join(column_evidence(code(), "EDWDM.CMP.vPush", "CampaignId").steps)
    assert "p.CampaignNk" in text
    assert "NCK.NotificationCampaignId" not in text


def test_a_plain_column_is_recognised() -> None:
    found = column_evidence(code(), "EDWDM.CMP.vPush", "RetryCount")
    assert found.kind in (KIND_PLAIN, KIND_LOGIC)
    assert "CASE" not in " ".join(found.steps)


def test_a_computed_column_shows_its_expression() -> None:
    text = " ".join(column_evidence(code(), "EDWDM.CMP.vPush", "PersonnelFlag").steps)
    assert "L.PartyId IS NOT NULL" in text
    assert "EDWUTIL.DTG.LKPParty" in text


def test_a_cte_column_brings_the_filters_that_shape_it() -> None:
    found = column_evidence(code(), "EDWDM.CMP.vCover", "Total15")
    text = " ".join(found.steps)
    assert found.kind == KIND_LOGIC
    assert "DATEADD(DAY,-15" in text
    assert "'6','10'" in text
    assert "DATEADD(YEAR,-2" in text


def test_a_flag_over_a_cte_column_reaches_the_same_filters() -> None:
    text = " ".join(column_evidence(code(), "EDWDM.CMP.vCover", "Cover15").steps)
    assert "Total15 > 0" in text
    assert "'6','10'" in text


def test_a_constant_in_a_load_procedure_is_found() -> None:
    found = column_evidence(code(), "EDWDM.TRE.vBehaviour", "BehaviourValue")
    assert found.kind == KIND_LOGIC
    assert "1 AS BehaviourValue" in " ".join(found.steps)


def test_a_sign_rule_in_a_join_reaches_the_plain_column_it_narrows() -> None:
    source = LOAD.replace(
        "INNER JOIN EDWSKEY.CMP.PushKey CPK ON STG.PushId = CPK.PushNk;",
        "INNER JOIN EDWSKEY.CMP.PushKey CPK ON STG.PushId = CPK.PushNk "
        "LEFT JOIN EDWSKEY.CMP.CrmKey CCK ON CAST(STG.CampaignId * -1 AS VARCHAR(50)) = CCK.Nk "
        "AND STG.CampaignId < 0 AND CCK.EdwSourceTable = 'Campaign';",
    )
    built = Code.build({"EDWDM.CMP.vPush": VIEW, "EDWLRY.CMP.ins_Push": source})
    found = column_evidence(built, "EDWDM.CMP.vPush", "CampaignId")
    text = " ".join(found.steps)
    assert found.kind == KIND_LOGIC
    assert "STG.CampaignId < 0" in text
    assert "EdwSourceTable" not in text


def test_the_view_filter_stays_at_object_level() -> None:
    built = code()
    assert "SystemDate" not in " ".join(
        column_evidence(built, "EDWDM.CMP.vPush", "RetryCount").steps
    )
    assert any("SystemDate" in part for part in object_scope(built, "EDWDM.CMP.vPush"))


def test_a_plain_column_is_plain() -> None:
    assert column_evidence(code(), "EDWDM.CMP.vPush", "RetryCount").kind == KIND_PLAIN


def test_constants_of_temporary_sets_are_collected() -> None:
    proc = TEMP_PROC.replace(
        "SELECT a.PartyId, 9 DefinitionId INTO #Leaving",
        "-- Gitmek uzere olan musteri\nSELECT a.PartyId, 9 DefinitionId INTO #Leaving",
    )
    built = Code.build(
        {
            "EDWDM.TRE.ins_Behaviour": proc,
            "EDWDM.TRE.vBehaviour": "CREATE VIEW TRE.vBehaviour AS SELECT T1.DefinitionId FROM [EDWDM].[TRE].[Behaviour] T1",
        }
    )
    text = " ".join(
        column_evidence(built, "EDWDM.TRE.vBehaviour", "DefinitionId").steps
    )
    assert "9: leaving" in text
    assert "Gitmek uzere" in text


def test_an_unqualified_column_in_a_joined_view_reaches_the_procedure_that_fills_it() -> (
    None
):
    code = Code.build(
        {
            "EDWDM.OTH.vMemzuc": """CREATE VIEW [OTH].[vMemzuc] AS
SELECT [Period], [AllBankRisk], I2.IdentityOrTAXId AS MaskedTaxNumberId
FROM [OTH].[Memzuc] AS M WITH(NOLOCK)
LEFT JOIN EDWUTIL.[DTG].[LKPIdentityNumber] AS I2 WITH(NOLOCK) ON I2.IdentityOrTAXNk = M.TaxNumber;""",
            "EDWDM.OTH.ins_Memzuc": """CREATE PROCEDURE [OTH].[ins_Memzuc] AS BEGIN
INSERT INTO #ReceivedData WITH(TABLOCK) (TaxNumber, [AllBankRisk])
SELECT R.TaxNumber, ISNULL(SUM(R.ShortTermRiskAmount + R.LongTermRiskAmount), 0) AS [AllBankRisk]
FROM [EDW].[OTH].[CreditRiskLimitReceivedData] AS R GROUP BY R.TaxNumber;
INSERT INTO [OTH].[Memzuc] ([TaxNumber], [AllBankRisk])
SELECT R.TaxNumber, SUM(ISNULL(R.[AllBankRisk], 0)) AS [AllBankRisk]
FROM #ReceivedData AS R GROUP BY R.TaxNumber;
END;""",
        }
    )

    evidence = column_evidence(code, "EDWDM.OTH.vMemzuc", "AllBankRisk")

    assert evidence.kind == KIND_LOGIC
    assert any("ShortTermRiskAmount" in step for step in evidence.steps)


def test_a_view_over_a_view_reaches_the_calculation_below() -> None:
    code = Code.build(
        {
            "EDWDM.ACT.vTop": "CREATE VIEW ACT.vTop AS SELECT T.Signal FROM ACT.vBase AS T",
            "EDWDM.ACT.vBase": """CREATE VIEW ACT.vBase AS
SELECT CASE WHEN S.Id IS NOT NULL THEN 'Var' ELSE 'Yok' END AS Signal FROM EDW.ACT.Source AS S""",
        }
    )

    evidence = column_evidence(code, "EDWDM.ACT.vTop", "Signal")

    assert evidence.kind == KIND_LOGIC
    assert any("'Var'" in step for step in evidence.steps)


def test_a_report_procedure_is_read_through_its_final_select() -> None:
    code = Code.build(
        {
            "EDWBridge.AIS.rpt_Segment": """CREATE PROCEDURE AIS.rpt_Segment AS BEGIN
SELECT P.CustomerPartyId, SUM(P.ProductCount) AS BankingProductTotalCount INTO #Products
FROM EDW.CON.Product AS P WHERE P.StatusId IN (1, 2) GROUP BY P.CustomerPartyId;
SELECT T.CustomerPartyId, ISNULL(T.BankingProductTotalCount, 0) AS BankingProductTotalCount
FROM #Products AS T;
END;""",
        }
    )

    evidence = column_evidence(
        code, "EDWBridge.AIS.rpt_Segment", "BankingProductTotalCount"
    )

    assert evidence.kind == KIND_LOGIC
    assert any("SUM(P.ProductCount)" in step for step in evidence.steps)


def test_new_rows_of_a_sync_get_their_code_evidence() -> None:
    from types import SimpleNamespace

    from app.services.dictionary_sync_describe import evidence_for

    column = SimpleNamespace(record={"ColumnName": "PersonnelFlag"}, is_new=True)
    old = SimpleNamespace(record={"ColumnName": "PushId"}, is_new=False)
    table = SimpleNamespace(key="EDWDM.CMP.vPush", is_new=False, columns=[column, old])

    found = evidence_for(
        [table], {"EDWDM.CMP.vPush": VIEW, "EDWLRY.CMP.ins_Push": LOAD}
    )

    assert any(
        "PartyId IS NOT NULL" in step
        for step in found[("edwdm.cmp.vpush", "personnelflag")]
    )
    assert ("edwdm.cmp.vpush", "pushid") not in found
    assert evidence_for([table], {}) == {}
