import { writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { apiContractJsonSchemas, API_CONTRACT_VERSION } from '../src/contracts/apiContracts.ts';

const outputPath = resolve('frontend/src/contracts/generated/api-contract-schemas.v1.json');
const payload = {
  version: API_CONTRACT_VERSION,
  endpoints: {
    config: { path: '/config', schema: apiContractJsonSchemas.config },
    owners: { path: '/owners', schema: apiContractJsonSchemas.owners },
    groups: { path: '/groups', schema: apiContractJsonSchemas.groups },
    portfolio: { path: '/portfolio/alice', schema: apiContractJsonSchemas.portfolio },
    transactions: { path: '/transactions', schema: apiContractJsonSchemas.transactions },
  },
};
writeFileSync(outputPath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
console.log(`Wrote ${outputPath}`);
