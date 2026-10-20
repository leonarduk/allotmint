// Set at build time by deploy-lambda.yml (release tag + short SHA, #11029).
export const UI_VERSION: string = import.meta.env.VITE_APP_VERSION || 'dev';
