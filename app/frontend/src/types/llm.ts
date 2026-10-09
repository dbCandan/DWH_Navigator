import type {components} from './api';

type Schemas = components['schemas'];

/** Model server connections (data-dictionary/PRDs/003-llm-connection, API contract). */
export type LlmIntegrationsState = Schemas['LlmIntegrationsState'];
export type LlmIntegrationItem = Schemas['LlmIntegrationItem'];
export type LlmIntegrationCreate = Schemas['LlmIntegrationCreate'];
export type LlmIntegrationCreated = Schemas['LlmIntegrationCreated'];
export type LlmIntegrationUpdate = Schemas['LlmIntegrationUpdate'];
export type LlmIntegrationUpdated = Schemas['LlmIntegrationUpdated'];
export type LlmModelState = Schemas['LlmModelState'];
export type LlmModelRow = Schemas['LlmModelRow'];
export type LlmModelsRequest = Schemas['LlmModelsRequest'];
export type LlmModelsResult = Schemas['LlmModelsResult'];
export type LlmInventory = Schemas['LlmInventory'];
export type LlmInventoryServer = Schemas['LlmInventoryServer'];
export type LlmTestRequest = Schemas['LlmTestRequest'];
export type LlmTestResult = Schemas['LlmTestResult'];
export type LlmTestStep = Schemas['LlmTestStep'];
