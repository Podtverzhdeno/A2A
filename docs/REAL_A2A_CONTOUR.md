# Closed real A2A contour

This project now supports a closed MVP contour where A3 talks to external A2
supplier agents over A2A, not through an in-process supplier mock.

## Start an external supplier

```powershell
$env:SUPPLIER_ID = "external-a2"
$env:SUPPLIER_CATALOG_FILE = "data\external-supplier-catalog.json"
$env:APP_PORT = "8204"
$env:PUBLIC_URL = "http://127.0.0.1:8204"
uv run a2a-supplier
```

The supplier publishes:

- `GET /.well-known/agent-card.json`
- JSON-RPC A2A endpoint at `/a2a`
- REST A2A routes from the SDK

## Register it in A3

Create an organization:

```powershell
$org = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/admin/organizations" `
  -ContentType "application/json" `
  -Body (@{
    legal_name = "External Supplier LLC"
    tax_id = "7700000004"
    roles = @("supplier")
  } | ConvertTo-Json)
```

Register the agent:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/admin/agents" `
  -ContentType "application/json" `
  -Body (@{
    organization_id = $org.organization_id
    agent_id = "external-a2"
    endpoint_url = "http://127.0.0.1:8204"
    categories = @("mro.standardized")
    hosting_mode = "external"
  } | ConvertTo-Json)
```

A3 will:

1. Load the external Agent Card.
2. Verify it declares the `procurement-rfq` skill.
3. Send a structured RFQ through the A2A SDK.
4. Activate the agent only if the endpoint returns a valid `quote` or
   `no_quote` artifact.
5. Add the agent to the live supplier registry without code changes.

## Re-check an agent

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/admin/agents/external-a2/check"
```

This refreshes the Agent Card and stores the latest contract-check result in
the registration record.
