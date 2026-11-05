// Compile-only deployment template. Nothing has been provisioned.
param location string = resourceGroup().location
param name string = 'evidence-desk'
param apiImage string
param webImage string
param postgresHost string
@secure()
param databaseUrl string
@secure()
param openaiApiKey string = ''
@secure()
param geminiApiKey string = ''
param mode string = 'DEMO'
param provider string = 'openai'
param model string = 'gpt-4.1-mini'
param publicOrigin string

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${name}-env'
  location: location
  properties: {}
}
resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: { external: true, targetPort: 3101, transport: 'http', allowInsecure: false }
      secrets: [
        { name: 'database-url', value: databaseUrl }
        { name: 'openai-key', value: openaiApiKey }
        { name: 'gemini-key', value: geminiApiKey }
      ]
    }
    template: {
      scale: { minReplicas: 1, maxReplicas: 1 }
      containers: [
        {
          name: 'web'
          image: webImage
          env: [{ name: 'API_URL', value: 'http://localhost:8000' }]
          resources: { cpu: json('0.5'), memory: '1Gi' }
          probes: [{ type: 'Readiness', httpGet: { path: '/api/health', port: 3101 }, initialDelaySeconds: 10, periodSeconds: 10 }]
        }
        {
          name: 'api'
          image: apiImage
          env: commonEnv
          resources: { cpu: json('0.5'), memory: '1Gi' }
          probes: [{ type: 'Readiness', httpGet: { path: '/api/health', port: 8000 }, initialDelaySeconds: 10, periodSeconds: 10 }]
        }
        {
          name: 'worker'
          image: apiImage
          command: ['python', 'services/worker/main.py']
          env: commonEnv
          resources: { cpu: json('0.5'), memory: '1Gi' }
        }
      ]
    }
  }
}
var commonEnv = [
  { name: 'DATABASE_URL', secretRef: 'database-url' }
  { name: 'OPENAI_API_KEY', secretRef: 'openai-key' }
  { name: 'GEMINI_API_KEY', secretRef: 'gemini-key' }
  { name: 'MODE', value: mode }
  { name: 'PROVIDER', value: provider }
  { name: 'MODEL', value: model }
  { name: 'PUBLIC_ORIGIN', value: publicOrigin }
  { name: 'COOKIE_SECURE', value: 'true' }
  { name: 'DEMO_LOGIN_ENABLED', value: mode == 'DEMO' ? 'true' : 'false' }
]
output hostname string = app.properties.configuration.ingress.fqdn
output databasePrerequisite string = '${postgresHost}: PostgreSQL with vector extension and TLS required; supplied externally'
