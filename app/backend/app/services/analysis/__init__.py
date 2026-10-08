"""Question analysis core (question-analysis PRD, Requirement 1 and 24).

Pure modules: Turkish normalization, term expansion, word search, column rules, table
aggregation and topic fit, the analyst's material, prompts and checks, the rule answer, the
single-question Excel report and the dictionary template parser. They take their inputs as
data objects and do no network, database or file access; the model is reached only through
the port in ``llm.port``.
"""
