# Proposal: Self-hosted Langfuse tracing for on-prem client deployments

<!-- tab: Proposal: Self-hosted Langfuse tracing for on-prem client deployments -->

# Proposal: Self-hosted Langfuse tracing for on-prem client deployments

2026-09-29 · @someone

## Summary and ask

We propose running a self-hosted Langfuse instance inside each client environment, so agent traces never leave the client network. LangSmith stays for internal development, staging and evals.

The first client can be in production in about 5–7 weeks. We need approval for the engineering time, a pilot client, and a decision on the Langfuse Enterprise license (it is the only way to get built-in data retention and audit logs on self-hosted).

## Background: how we trace today

All agent traces go to LangSmith cloud on our paid plan (project `firefly-prod`, endpoint `api.smith.langchain.com`, 180-day retention). The agents are built on LangGraph and call our own vision reasoning model.

Each client application has a scheduler that runs 8–10 operations a day:

- **Two aggregations:** user account aggregation and entitlement aggregation. These pull every user and entitlement from the app, so they are the heaviest and slowest jobs.
- **JML operations:** create user, add entitlement, remove entitlement, update, remove user, and similar targeted changes.
- **Reruns:** some operations run more than once a day.

For a 30-app client that is about 240–300 scheduled jobs a day, or 7,000–9,000 traces a month before reruns. Volume grows linearly with apps and clients.

The heaviest run seen so far was an account aggregation on one app with about 130,000 accounts. It ran for 75.6 minutes.

## Problems with the current setup

The current setup sends customer identity data to a third-party SaaS and still fails to capture our largest runs.

| Problem | Evidence | Impact |
| --- | --- | --- |
| Customer data leaves the client network | Production traces go to LangSmith's US cloud. Our [product page](https://redblock.ai/product) says sensitive data stays under the client's control. | A customer security review could flag this as data egress. It conflicts with our positioning. |
| Payloads far above trace limits | The 130K-account aggregation had a 222 MB input and a 338 MB output. LangSmith's limit is 25 MB, so both were dropped. | We pay for traces that don't hold the data. Serializing huge LangGraph state also slows the job. |
| Credentials and PII in traces | Password, certificate and secret rotation runs, plus aggregation outputs with names, emails and entitlements. | Security exposure in any trace store, whichever tool we use. |
| Isolated or air-gapped clients | SaaS tracing needs outbound internet access. | No tracing at all for those clients. |

The payload problem has to be fixed whichever tool we use. Langfuse users have reported a [4.5 MB ingestion limit](https://github.com/orgs/langfuse/discussions/7175), which is stricter than LangSmith's.

## Why Langfuse

Langfuse is the only one of the two we can run free and offline inside a client network. We keep LangSmith where it is strongest: internal work on LangChain and LangGraph.

|  | Langfuse (self-hosted) | LangSmith |
| --- | --- | --- |
| License | MIT core. Some Enterprise add-ons need a paid key. | Proprietary, closed source |
| Self-hosting | Free, with full feature parity with Langfuse Cloud | Only on an Enterprise contract |
| Internet access | Not required | SaaS needs outbound access |
| Framework fit | LangChain/LangGraph callback plus OpenTelemetry; framework-agnostic | Deepest with LangChain and LangGraph |
| Evals and alerting | Evaluators and monitors; more do-it-yourself | More turnkey evals and alerting, plus managed agent deployment |
| Cost | Software free; we pay for infrastructure | Plus plan $39 per seat a month; base traces $2.50 per 1,000 over the included amount |

Ownership: [ClickHouse acquired Langfuse in January 2026](https://langfuse.com/blog/joining-clickhouse). The MIT license and self-hosting were confirmed as unchanged. LangSmith pricing is from an [August 2026 comparison](https://altaitools.com/langfuse-vs-langsmith/), not LangChain's own page.

## Proposed architecture

Each client gets its own Langfuse instance next to our agents, and no trace data leaves the client network.

[Embedded widget: architecture inside one client · 7 components](node/b9ff126c-89bd)

Agents send traces to Langfuse web over the internal network. The web container queues events in Valkey and object storage, and the worker writes them to ClickHouse. Only Redblock engineers with VPN and SSO access can open the UI. [Langfuse does not need internet access](https://langfuse.com/self-hosting/security/networking), so the same design works for air-gapped clients.

Every component, what it stores and how it scales: [System design](file/477a9e12-6274)

## Deployment: Kubernetes with the Helm chart

Every client runs Langfuse on Kubernetes with the [Langfuse Helm chart v2](https://langfuse.com/self-hosting/deployment/kubernetes-helm). One deployment model means one bundle to build, test and support; the single-VM option is dropped.

Where the cluster comes from:

- **Client has Kubernetes** (OpenShift, Rancher or vanilla): we install into a namespace on their cluster.
- **Client runs on a cloud:** their EKS, AKS or GKE.
- **No Kubernetes:** the client provides VMs and we install [k3s](https://github.com/k3s-io/k3s), or [RKE2](https://github.com/rancher/rke2) for hardened or FIPS environments. Both are Apache 2.0.

| Component | Size S (up to 30 apps) | Sizes M and L (up to 300 apps) |
| --- | --- | --- |
| Langfuse web | 2 replicas × 2 vCPU, 4 GB | 2–3 replicas |
| Langfuse worker | 1 replica × 2 vCPU, 4 GB | 2–3 replicas |
| ClickHouse | 3 replicas × 2 vCPU, 8 GB, 100 GB disk, plus 3 Keepers | 3 replicas × 4 vCPU, 16–32 GB, 300–500 GB disk |
| Postgres, Valkey, object storage | Bundled with the chart, or the client's managed services | Same |
| **Nodes** | **3 × 8 vCPU, 32 GB** | **5–7 nodes, 40–56 vCPU** |

Every resource by name, per size and per cloud: [Bill of materials](file/ca72c7f4-2fb7)

Langfuse recommends [at least 3 ClickHouse replicas in production](https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse); the count can't be raised later without manual work or downtime. The cluster needs Kubernetes 1.28 or newer, cert-manager and the ClickHouse Kubernetes Operator. Minimum versions are ClickHouse 25.12 (26.4 recommended), PostgreSQL 15 (16 recommended) and Valkey 8, per the [v4 requirements](https://langfuse.com/self-hosting/upgrade/upgrade-guides/upgrade-v3-to-v4). Every component must run in UTC.

Langfuse runs on its own nodes or node pool, never beside the browser and vision agents. Both are CPU-heavy and would slow each other down.

The trade-off: a small client now needs three nodes (24 vCPU, 96 GB in total) instead of one 8 vCPU VM. In return, every client gets high availability and the same install path.

## Storage estimate and data retention

A 30-app client needs about 100 GB of ClickHouse disk per replica and 250 GB of object storage for 90 days of traces. These are our estimates; the staging phase measures the real numbers.

| Item | Estimate for a 30-app client |
| --- | --- |
| Jobs per day | About 300 |
| Observations per day | About 25,000 (about 750,000 a month), assuming 200 per aggregation and 50 per JML job |
| Raw event data per day, after payload cleanup | 125–250 MB, at 5–10 KB per observation |
| Screenshots, if every one is kept | About 1 GB a day, at about 200 KB each |
| Screenshots, if kept only on failures | Negligible |

Screenshots are the biggest variable, so the screenshot policy is a decision for this proposal.

On self-hosted Langfuse, [data retention is an Enterprise feature](https://langfuse.com/docs/administration/data-retention). Without it, data is kept forever by default. Our options:

- **Buy the Enterprise license.** Retention is set per project, with a 3-day minimum, and runs nightly across ClickHouse and object storage.
- **Run open source with workarounds.** Add a [lifecycle rule on the events bucket](https://langfuse.com/self-hosting/configuration/scaling) (Langfuse suggests 30 days, never on the media bucket) plus scheduled deletion. These need re-checking on every upgrade.

Either way, we disable ClickHouse's system log tables, which Langfuse notes can take up most of the disk.

## Licensing and cost

The open-source edition covers everything we need for tracing at no license cost, including deployment inside a customer's environment. The MIT license allows commercial use and redistribution as long as the copyright and license notice are kept.

Every component's license, and the exact resources per size tier and deployment model: [Bill of materials](file/ca72c7f4-2fb7)

These features need a paid [Enterprise license key](https://langfuse.com/self-hosting/license-key), even when self-hosted:

- Data retention policies
- Audit logs
- Project-level RBAC roles and protected prompt labels
- Server-side data masking
- UI customization (needed if we want to white-label it)
- Organization management API, SCIM, organization creators and the instance management API

Security-focused clients often ask for retention, audit logs and RBAC, so the Enterprise license may pay for itself.

Open questions on cost:

- Langfuse's self-hosted Enterprise price: we need a quote from their team.
- Who pays for the infrastructure at each client: the client's hardware, or bundled into our price.
- How much our LangSmith bill drops once production traces move off it.

## Engineering work on our side

Payload cleanup is the largest piece of work, and it also improves LangSmith today.

1. **Instrumentation**
   - Add the Langfuse Python SDK (4.7.0 or later) with its LangGraph callback handler, next to LangSmith.
   - Put tracing behind a config switch: `langsmith`, `langfuse`, `both` or `off`, set per deployment.
   - Set `session_id` to the job ID and tags to the operation. Add metadata for client, app name, attempt number (so reruns are visible), revision ID and scheduler run ID.
   - Flush the SDK at the end of every job, which matters for 75-minute runs.
2. **Payload cleanup**
   - Keep bulk account and entitlement data out of LangGraph state. Write it to disk, a database or object storage, and keep only a reference, count and checksum in state.
   - Replace large lists with summaries in traces: count, size, checksum, storage reference and a few redacted samples.
   - Mask passwords, certificates, API keys and tokens in the SDK before anything is sent.
   - Add progress metadata (page number, accounts fetched so far) instead of raw payloads.
   - Apply the chosen screenshot policy.
3. **Packaging**
   - Ship Helm values and install scripts for the Langfuse chart v2 in our release, plus k3s or RKE2 install scripts for clients without Kubernetes.
   - Use headless initialization to pre-create the organization, project and API keys, and turn off open sign-up and telemetry. Langfuse has no default admin account.
   - Pull images from Docker Hub directly, not `docker.langfuse.com`, which records each pull for Langfuse's analytics. Mirror them for air-gapped clients.
   - Point LLM-as-judge evals at our own model endpoint, so nothing goes to an external AI provider.
4. **Operations**
   - Nightly Postgres dumps and ClickHouse backups to client storage.
   - Health checks on web (port 3000) and worker (port 3030), and disk alerts at 80%.
   - Pinned image versions, tested in our staging before each client rollout.
   - A runbook for install, upgrade, backup restore and troubleshooting.

## What we need from each client

This checklist goes into the client onboarding pack, so approvals start early.

- [ ] A Kubernetes namespace sized for their tier, or VMs for us to install Kubernetes on, with a storage class that allows volume expansion, and permission to install cert-manager and the ClickHouse operator
- [ ] S3-compatible object storage, or permission to run SeaweedFS
- [ ] An internal DNS name and TLS certificate for the Langfuse URL
- [ ] Network access from the agent hosts to Langfuse web on port 443
- [ ] Access for Redblock engineers: VPN or a jump host, plus SSO through their identity provider (Okta or Entra)
- [ ] A container registry mirror, if the environment is air-gapped
- [ ] A backup target
- [ ] Their required retention period for traces

## Timeline and rollout plan

The first client reaches production in about 5–7 weeks. Each client after that takes one to two days of install, plus their approvals.

[Embedded widget: rollout plan · 4 phases, 3 gates](node/218c2a78-32bc)

Both build streams run in parallel, and each gate must pass before the next phase starts. The client's security review is the least predictable step.

## Risks and mitigations

The biggest schedule risk is the client's security review; the biggest operational risk is disk growth without retention.

| Risk | Mitigation |
| --- | --- |
| Client security review delays the pilot | Pick a client we already work closely with. Send the architecture and data-flow description up front. |
| Payload cleanup takes longer than planned | Start it first. It pays off on LangSmith even before Langfuse ships. |
| ClickHouse disk fills up without retention | Disk alerts at 80%, ClickHouse system logs disabled, and either the Enterprise license or lifecycle rules. |
| Running many separate instances becomes a support burden | One tested bundle, pinned versions, and a runbook. |
| No view across clients | Accept it, or export aggregated, sanitized metrics where a client agrees. |
| Large spans rejected by Langfuse ingestion | Summaries keep spans small. The staging phase replays the 130K-account aggregation to confirm. |
| Engineers can't reach a client's instance when debugging | Make VPN and SSO access a client prerequisite. |
| Client has no Kubernetes | We install k3s or RKE2 on VMs they provide. Ask about Kubernetes in the first technical call. |

## Decisions needed

These eight decisions unblock the work; the first four are needed before phase 1 starts.

1. Approve the approach: Langfuse per client for production, LangSmith for internal work.
2. Kubernetes for clients without a cluster: k3s, or RKE2 for hardened environments. (Packaging is decided: Kubernetes with the Helm chart for every client.)
3. Whether to buy the Langfuse Enterprise license, or run open source with retention workarounds.
4. Which client runs the pilot.
5. Screenshot policy: keep all, or only on failures and retries.
6. Default trace retention per client, for example 30 or 90 days.
7. Who pays for the infrastructure at each client.
8. Owners for the four engineering workstreams.

## Sources

- [Langfuse: Self-hosting overview](https://langfuse.com/self-hosting)
- [Langfuse: Migrate v3 to v4 (infrastructure requirements)](https://langfuse.com/self-hosting/upgrade/upgrade-guides/upgrade-v3-to-v4)
- [Langfuse: Scaling and minimum requirements](https://langfuse.com/self-hosting/configuration/scaling)
- [Langfuse: ClickHouse](https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse)
- [Langfuse: Docker Compose deployment](https://langfuse.com/self-hosting/deployment/docker-compose)
- [Langfuse: Application containers](https://langfuse.com/self-hosting/deployment/infrastructure/containers)
- [Langfuse: Networking](https://langfuse.com/self-hosting/security/networking)
- [Langfuse: Data retention](https://langfuse.com/docs/administration/data-retention)
- [Langfuse: Enterprise license key (self-hosted)](https://langfuse.com/self-hosting/license-key)
- [Langfuse joins ClickHouse](https://langfuse.com/blog/joining-clickhouse)
- [Langfuse discussion #7175: ingestion size limit](https://github.com/orgs/langfuse/discussions/7175)
- [Alt AI Tools: Langfuse vs LangSmith 2026](https://altaitools.com/langfuse-vs-langsmith/)
- [Redblock: Product](https://redblock.ai/product)

<!-- tab: System design -->

# System design

Each client runs one self-contained Langfuse v4 stack: two stateless application containers and four data stores. Everything scales inside that client, and no trace data is shared between clients.

## At a glance: one trace, end to end

A trace passes through five steps and four stores, and never leaves the client network.

[Embedded widget: one trace, end to end · 5 steps, 4 stores](node/95fb3f7a-b278)

Steps 1 and 2 run in our code on the agent host; steps 3 to 5 run in the Langfuse stack. Because the event sits in object storage before the worker touches it, a slow or down ClickHouse delays traces rather than losing them.

## Redblock side: what we build into the agents

Five pieces live in our agent code and ship in every release. They decide what reaches Langfuse, so they matter more for cost and safety than anything on the server.

| Component | What it does | Scaling note |
| --- | --- | --- |
| Scheduler | Starts 8–10 jobs per app per day, including reruns | Trace volume follows job count, so it grows with apps |
| LangGraph agents | Run the job: plan actions, drive the app's interface, verify the result | Each graph node becomes an observation; fewer, larger nodes mean fewer rows |
| Tracing layer | Langfuse Python SDK with its LangChain callback handler, behind a switch: `langsmith`, `langfuse`, `both` or `off`. Sets session, tags and metadata. | Exports in background batches, so tracing never blocks a job; flush at job end |
| Payload store | Writes bulk account and entitlement data to local disk or object storage. Graph state keeps only a reference, count and checksum. | Keeps observations around 5–10 KB, far under the 4.5 MB ingestion limit |
| Masking | Replaces passwords, keys, tokens, certificates and personal data before export | Runs in our process, so it costs the server nothing and needs no Enterprise license |
| Screenshot policy | Attaches screenshots only on failures, retries and verification steps (if we choose that) | Screenshots are the largest storage variable: about 1 GB a day for 30 apps if all are kept |

One rule holds everywhere: a tracing failure must never fail a job. If Langfuse is down, the job still completes; at worst its trace is lost.

## Langfuse stack: each component

Two containers do the work and hold no state; four stores hold all the data. That split is what makes scaling simple: add containers for throughput, add memory and disk to the stores for volume.

| Component | Role | What it stores | How it scales | If it goes down (expected) |
| --- | --- | --- | --- | --- |
| Langfuse web | Serves the UI and public API. Receives trace batches over OpenTelemetry, writes each batch to object storage and queues a reference in Valkey. | Nothing | More replicas behind the load balancer; add one when CPU passes 50% | Agents can't export (jobs keep running); UI unavailable |
| Langfuse worker | Takes queued references, reads the events from object storage and writes them to ClickHouse. Also runs evals, exports and retention jobs. | Nothing | More replicas; scale on CPU above 50% or on queue depth | Queue grows; events wait in object storage, nothing is lost |
| ClickHouse | Column database behind every table, filter and dashboard | All traces, observations and scores, compressed | Vertically: more memory (16 GB+ for larger deployments) and disk. One shard holds several TB. 3 replicas for high availability. | UI and API reads fail; ingestion waits in the queue |
| PostgreSQL | Transactional database | Users, organizations, projects, API keys, prompts, datasets, settings | Stays small; vertical only. The client's managed Postgres works. | Most of the UI and API fail |
| Valkey | Ingestion queue; cache for API keys and prompts | Queue entries (references, not payloads) and cache | 4 CPUs if CPU passes 90%; cluster mode; shard the queues at very high load | Ingestion stops until it's back |
| Object storage | First landing place for every event; media uploads; exports | Raw events, screenshots, media | Grows with volume; raise concurrent writes if sockets saturate | Ingestion fails |
| Load balancer | TLS termination and routing to web replicas | Nothing | The client's existing ingress | Langfuse unreachable |
| LLM endpoint (optional) | Only for LLM-as-judge evals and the playground | Nothing | Our own model endpoint | Only those features stop |

The object-storage-first design comes from [Langfuse's architecture](https://langfuse.com/self-hosting): every event is persisted there before any database write, so a database outage delays traces instead of dropping them. The scaling signals are from Langfuse's [scaling guide](https://langfuse.com/self-hosting/configuration/scaling); the failure column is our reading of that design, to be confirmed in staging.

## How our jobs map onto Langfuse

One scheduled job becomes one trace, and every graph node or model call inside it becomes an observation. Consistent attributes are what keep traces searchable at 30 apps or 300.

| Langfuse concept | Redblock value | Why |
| --- | --- | --- |
| Project | One per client deployment, plus `staging` where the client has one | Access and retention are set per project |
| Trace (root observation) | One scheduled job | One row per job in the default view |
| Session | `job_id`, as today | Groups everything that belongs to one job |
| Observations | LangGraph nodes, model calls (generations), browser and tool steps | Where latency and failures show up |
| Tags | Operation, for example `ACCOUNT_AGGREGATION_V2` or `REMOVE_USER` | Filter by job type |
| Metadata | Client, app name, attempt number, revision ID, scheduler run ID | Filter by app; spot reruns |
| Scores | Post-action verification result (pass or fail), plus counts such as accounts fetched | Success rate per app and operation without opening traces |
| Environment | `production` or `staging` | Keeps test runs out of dashboards |

Langfuse v4 stores each observation once, with all trace-level attributes copied onto it, so filtering by tag or metadata needs no joins. The Python SDK 4.7.0 or later does that copying on our side ([v4 changes](https://langfuse.com/changelog/2026-08-17-langfuse-v4)).

## Scaling within a client

Volume grows linearly with apps: about 830 observations per app per day at today's job mix. Every size runs on Kubernetes; what grows is node count, ClickHouse memory and disk.

| Client size | Jobs per day | Observations per day | Event data per day | Raw data over 90 days | Size (Bill of materials) |
| --- | --- | --- | --- | --- | --- |
| 30 apps | \~300 | \~25K | 125–250 MB | 11–22 GB | S |
| 100 apps | \~1,000 | \~83K | 0.4–0.8 GB | 37–75 GB | M |
| 300 apps | \~3,000 | \~250K | 1.2–2.5 GB | 110–225 GB | L |

These assume 5–10 KB per observation after the payload cleanup, before ClickHouse compression and without screenshots. The staging phase replaces them with measured numbers. Even at 300 apps we stay far below what one ClickHouse shard holds, which is several terabytes.

What to scale, and when:

| Signal | Component | Action |
| --- | --- | --- |
| Worker CPU above 50%, or `langfuse.queue.ingestion.depth` (waiting) keeps rising | Worker | Add worker replicas |
| Web CPU above 50% | Web | Add web replicas |
| UI slow while ingestion is busy | Web | Run a second, ingestion-only web deployment for `/api/public/otel*`, `/api/public/ingestion*` and `/api/public/media*` |
| Slow queries even with time filters | ClickHouse | More memory; 16 GB or more for larger deployments |
| Disk above 80% | ClickHouse, object storage | Expand the volume, turn off ClickHouse system log tables, enforce retention |
| Valkey CPU above 90% | Valkey | 4 CPUs, cluster mode, then shard the ingestion queues |
| "socket usage at capacity" warnings on web | Object storage client | Raise `LANGFUSE_S3_CONCURRENT_WRITES` above 50, in small steps |
| Observations grow faster than apps | Agents | Trace fewer, larger steps; sample successful JML runs if needed |

## Scaling across clients

A new client adds an instance, not load on a shared system: each stack is sized for its own client. What grows with client count is our operations work.

[Embedded widget: how we run many clients · 1 release, N instances](node/b891feba-37fd)

- **One release bundle** per Redblock release, with Langfuse pinned. Per-client settings (hostnames, storage, SSO, size) live in one Helm values file per client.
- **Upgrades roll out client by client** after staging, inside each client's change window.
- **Same health checks and alert thresholds everywhere,** so support looks identical across clients.
- **Open question:** a small registry of which client runs which version and tier. It holds no trace data.

## Availability, backups and failures

Events land in object storage before any database, so a ClickHouse outage delays traces instead of losing them. Our agents never wait on tracing.

| Component | How it stays available on Kubernetes |
| --- | --- |
| Web and worker | 2 or more replicas each (1 worker at size S), spread across nodes |
| ClickHouse | 3 replicas and 3 Keepers, one per node |
| Postgres and Valkey | The client's managed services, or replicated in-cluster at size L |
| Backups | Nightly Postgres dump and ClickHouse backup to client storage, plus volume snapshots |
| Losing a node | ClickHouse and web keep serving; single-replica pods restart on another node |

- **Recovery order:** object storage and Postgres, then ClickHouse and Redis, then worker and web.
- **Upgrades:** pinned image versions, tested in our staging, then applied per client. Langfuse runs long migrations in the [background](https://langfuse.com/self-hosting), which keeps downtime short.
- **Open question:** each client's recovery targets, meaning how much trace history they can lose and how fast it must come back.

## Security

Only the Langfuse web container is reachable, and only from inside the client network.

- **Network:** agents reach Langfuse web on port 443 through the client's load balancer, which terminates TLS. Postgres, ClickHouse, Valkey and the worker stay on a private network. [No outbound internet is needed](https://langfuse.com/self-hosting/security/networking); the one outbound call, an update check, fails quietly.
- **Access:** sign-in through the client's identity provider (SSO), open sign-up turned off, and the first organization, project and API keys created by headless initialization. Project-level roles need the Enterprise license.
- **Encryption:** TLS in transit. At rest, ClickHouse disk encryption and the client's encrypted object storage. Langfuse's `ENCRYPTION_KEY` protects secrets it stores.
- **Secrets in traces:** masked in the SDK before export, so credentials never reach any store.
- **Images:** pulled from Docker Hub and mirrored into the client's registry, not pulled through Langfuse's analytics endpoint.
- **External AI:** evals, if used, call only our own model endpoint.

## Monitoring Langfuse itself

We watch four signals per client, through the client's existing monitoring where they have it.

- Health checks on web (port 3000) and worker (port 3030).
- Worker queue depth, published over StatsD as `langfuse.queue.ingestion.depth`: the main scaling signal.
- Disk use on ClickHouse and object storage, alerting at 80%.
- Container CPU and memory, with the Node.js heap set through `NODE_OPTIONS=--max-old-space-size` to match the container's memory ([containers guide](https://langfuse.com/self-hosting/deployment/infrastructure/containers)).

## Tech stack and versions

We standardize on one version set per release and test it in staging before any client gets it.

| Layer | What we use | Version |
| --- | --- | --- |
| Tracing server | Langfuse web and worker images | Latest v4 release, pinned |
| Analytics store | ClickHouse | 26.4 recommended, 25.12 minimum |
| Transactional store | PostgreSQL | 16 recommended, 15 minimum |
| Queue and cache | Valkey (not Redis, for licensing) | 8 or newer |
| Object storage | The client's S3, or SeaweedFS | S3-compatible API |
| Kubernetes | The client's cluster; EKS, AKS or GKE; or k3s or RKE2 on client VMs | 1.28 or newer |
| Packaging | Langfuse Helm chart, ClickHouse Kubernetes Operator, cert-manager | Chart v2 |
| Agent SDK | Langfuse Python SDK with its LangChain callback, built on OpenTelemetry | 4.7.0 or later |
| Agent framework | LangGraph on langchain-core | As today (langchain-core 1.4.6) |

All components run on UTC; Langfuse returns wrong or empty results otherwise ([ClickHouse guide](https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse)).

## Sources

- [Langfuse: Self-hosting overview and architecture](https://langfuse.com/self-hosting)
- [Langfuse: Scaling and minimum requirements](https://langfuse.com/self-hosting/configuration/scaling)
- [Langfuse: ClickHouse](https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse)
- [Langfuse: Application containers](https://langfuse.com/self-hosting/deployment/infrastructure/containers)
- [Langfuse: Networking](https://langfuse.com/self-hosting/security/networking)
- [Langfuse: Migrate v3 to v4 (data model and versions)](https://langfuse.com/self-hosting/upgrade/upgrade-guides/upgrade-v3-to-v4)
- [Langfuse v4 changelog](https://langfuse.com/changelog/2026-08-17-langfuse-v4)
- [Langfuse: Docker Compose deployment](https://langfuse.com/self-hosting/deployment/docker-compose)
- [Langfuse discussion #7175: ingestion size limit](https://github.com/orgs/langfuse/discussions/7175)

<!-- tab: Bill of materials -->

# Bill of materials

Every component we ship is open source and can run on client premises, as long as we use Valkey instead of Redis, SeaweedFS or the client's S3 instead of MinIO, and turn off Langfuse's telemetry. Every client runs on Kubernetes with the Langfuse Helm chart. Sizes below are starting points from Langfuse's minimums and our volume estimates; the staging phase confirms them.

## Licenses: can we ship it to clients?

Everything we plan to install is under a permissive or OSI-approved license. The only paid part is Langfuse's Enterprise code, which stays off unless we buy a key.

| Component | What we ship | License | Ship to client premises? |
| --- | --- | --- | --- |
| [Langfuse](https://github.com/langfuse/langfuse/blob/main/LICENSE) web and worker | `langfuse/langfuse:4`, `langfuse/langfuse-worker:4` | MIT, except the `ee/` folders (proprietary, need a license key) | Yes. Enterprise code is in the image but inactive without a key. |
| [Langfuse Python SDK](https://github.com/langfuse/langfuse-python) | `langfuse` package, v4 | MIT | Yes |
| [Langfuse Helm chart](https://github.com/langfuse/langfuse-k8s) v2 | Chart plus its bundled sub-charts | MIT | Yes. v2 has no Bitnami images. |
| [ClickHouse](https://github.com/ClickHouse/ClickHouse) server and Keeper | `clickhouse/clickhouse-server` | Apache 2.0 | Yes |
| [ClickHouse Kubernetes Operator](https://github.com/ClickHouse/clickhouse-operator) | Official operator | Apache 2.0 | Yes (Kubernetes only) |
| [PostgreSQL](https://www.postgresql.org/about/licence/) | `postgres:17` | PostgreSQL License | Yes |
| [Valkey](https://github.com/valkey-io/valkey) | `valkey/valkey:8` | BSD-3-Clause | Yes |
| [SeaweedFS](https://github.com/seaweedfs/seaweedfs) | S3-compatible object storage | Apache 2.0 | Yes (a separate paid Enterprise edition exists; we don't need it) |
| [cert-manager](https://github.com/cert-manager/cert-manager) | Certificate management | Apache 2.0 | Yes (Kubernetes only) |
| [Redis](https://redis.io/legal/licenses/) 7.4 | Not shipped | RSALv2 or SSPLv1 (source-available, not open source) | No. Replaced by Valkey. |
| Redis 8 | Not shipped | RSALv2, SSPLv1 or AGPLv3 | No. AGPL adds copyleft obligations. |
| [MinIO](https://en.wikipedia.org/wiki/MinIO) | Not shipped | AGPLv3; community edition in maintenance mode | No. Replaced by SeaweedFS. |

Managed cloud services (RDS, ElastiCache, Azure Managed Redis, Cloud SQL and so on) run under the cloud provider's terms, which the client already accepts.

Open question for Langfuse sales: if we buy the Enterprise license, is it priced per instance, and does it cover a vendor installing Langfuse at many clients? Their [self-hosted pricing page](https://langfuse.com/pricing-self-host) doesn't say.

This is not legal advice. Have legal review the list before the first client ships.

## Changes from our earlier plan

Four changes, all driven by the license check above.

1. **Valkey 8 replaces Redis.** Langfuse's own Compose file uses `redis:7`, which currently resolves to Redis 7.4 under RSALv2/SSPL. Langfuse [officially supports Valkey 8+](https://langfuse.com/self-hosting/deployment/infrastructure/cache), and its Helm chart v2 already bundles it.
2. **SeaweedFS, or the client's S3, replaces MinIO.** MinIO stopped publishing images in October 2025 and entered maintenance mode in December 2025, [per It's FOSS](https://itsfoss.com/news/minio-moves-away-from-open-source/). SeaweedFS is [officially supported by Langfuse](https://langfuse.com/self-hosting/deployment/infrastructure/blobstorage) and is the Helm chart's default. Langfuse still recommends a managed store (S3, Azure Blob, GCS) where the client has one.
3. **Telemetry off.** Self-hosted Langfuse [sends usage telemetry to eu.posthog.com by default](https://langfuse.com/self-hosting/security/telemetry). We set `TELEMETRY_ENABLED=false` on web and worker.
4. **Images from Docker Hub or the client's mirror.** Langfuse's templates pull through `docker.langfuse.com`, which records each pull. We pull `docker.io/langfuse/...` directly and mirror everything into the client's registry.

## Size tiers

We size each client by app count. Even the largest tier averages about 3 observations a second, so compute barely grows between tiers; disk and redundancy do.

| Tier | Apps | Jobs per day | Observations per day | Raw event data, 90 days | Kubernetes nodes |
| --- | --- | --- | --- | --- | --- |
| S | Up to 30 | \~300 | \~25K | 11–22 GB | 3 nodes: 24 vCPU, 96 GB |
| M | 31–100 | \~1,000 | \~83K | 37–75 GB | 5 nodes: 40 vCPU, 160 GB |
| L | 101–300 | \~3,000 | \~250K | 110–225 GB | 6–7 nodes: 48–56 vCPU, 288–320 GB |

Raw data assumes 5–10 KB per observation after payload cleanup, before ClickHouse compression. Keeping every screenshot adds about 90 GB (S), 300 GB (M) or 900 GB (L) over 90 days. Above 300 apps, we size from staging measurements.

## Containers and resources per tier

These are the same on any Kubernetes cluster. Cells read replicas × CPU and memory, plus disk.

| Component | Image (pin an exact version) | S | M | L |
| --- | --- | --- | --- | --- |
| Langfuse web | `docker.io/langfuse/langfuse:4` | 2 × 2 vCPU, 4 GB | 2 × 2 vCPU, 4 GB | 3 × 2 vCPU, 4 GB |
| Langfuse worker | `docker.io/langfuse/langfuse-worker:4` | 1 × 2 vCPU, 4 GB | 2 × 2 vCPU, 4 GB | 3 × 2 vCPU, 4 GB |
| ClickHouse server | `docker.io/clickhouse/clickhouse-server:26.4` | 3 × 2 vCPU, 8 GB, 100 GB | 3 × 4 vCPU, 16 GB, 300 GB | 3 × 4 vCPU, 32 GB, 500 GB |
| ClickHouse Keeper | Deployed by the operator | 3 × 1 vCPU, 2 GB, 10 GB | 3 × 1 vCPU, 2 GB, 10 GB | 3 × 1 vCPU, 2 GB, 10 GB |
| PostgreSQL | `docker.io/postgres:17` | 2 vCPU, 4 GB, 20 GB | 2 vCPU, 8 GB, 50 GB | 2 vCPU, 8 GB, 50 GB, plus a standby |
| Valkey | `docker.io/valkey/valkey:8` | 1 vCPU, 2 GB | 1 vCPU, 2 GB | 2 vCPU, 4 GB, plus a replica |
| SeaweedFS (if no client S3) | `docker.io/chrislusf/seaweedfs` | 2 vCPU, 4 GB, 250 GB | 2 vCPU, 4 GB, 750 GB | 3 × 2 vCPU, 4 GB, 1.5 TB total |
| Load balancer and TLS | The client's existing one | — | — | — |

Web, worker, Postgres and Valkey follow Langfuse's [minimum requirements](https://langfuse.com/self-hosting/configuration/scaling). Keeper sizing follows Langfuse's own [AWS Terraform module](https://github.com/langfuse/langfuse-terraform-aws). Object storage covers raw events plus every screenshot kept for 90 days.

Langfuse needs no GPU and no LLM of its own. The only model touchpoints are optional: LLM-as-judge evals pointed at our own model endpoint, and a custom model definition for our vision model so token counts show per model.

## Where the cluster comes from

Every client gets the same Helm install; only the cluster underneath differs.

| Client situation | Cluster | Storage for ClickHouse | Notes |
| --- | --- | --- | --- |
| Has Kubernetes 1.28+ (OpenShift, Rancher, vanilla) | A namespace on their cluster | Their CSI storage class, with volume expansion | They approve cert-manager and the ClickHouse operator |
| Runs on AWS, Azure or GCP | Their EKS, AKS or GKE | gp3, Premium SSD or pd-balanced | Resource names in the sections below |
| No Kubernetes | We install [k3s](https://github.com/k3s-io/k3s), or [RKE2](https://github.com/rancher/rke2) for hardened or FIPS environments, on VMs they provide (both Apache 2.0) | Their SAN's CSI driver, or [Longhorn](https://github.com/longhorn/longhorn) (Apache 2.0, a CNCF project) | VMs match the node specs below; Ubuntu 24.04 LTS or RHEL 9 |

k3s's built-in storage is a local-path provisioner, so for ClickHouse we add a proper storage layer. RKE2 is built to pass the CIS Kubernetes Benchmark and supports FIPS 140-2, which suits government and regulated clients.

## Node pools per size

The same shape works on the client's own cluster (OpenShift, Rancher, vanilla) or a managed one. ClickHouse gets its own nodes from tier M, one replica per node.

| Node pool | S | M | L |
| --- | --- | --- | --- |
| Shared pool (all components) | 3 × 8 vCPU, 32 GB | — | — |
| General pool (web, worker, operators; Postgres, Valkey and SeaweedFS if in-cluster) | — | 2 × 8 vCPU, 32 GB | 3 × 8 vCPU, 32 GB (4 if Postgres, Valkey and SeaweedFS run in-cluster) |
| ClickHouse pool (server + Keeper) | — | 3 × 8 vCPU, 32 GB | 3 × 8 vCPU, 64 GB |
| ClickHouse volume per replica | 100 GB SSD | 300 GB SSD | 500 GB SSD |
| Totals | 24 vCPU, 96 GB | 40 vCPU, 160 GB | 48–56 vCPU, 288–320 GB |

Prerequisites, per Langfuse's [Helm guide](https://langfuse.com/self-hosting/deployment/kubernetes-helm):

- Kubernetes 1.28 or newer
- cert-manager and the ClickHouse Kubernetes Operator, installed before the chart
- A storage class with volume expansion enabled
- The client's ingress controller or Gateway API implementation, an internal DNS name and a TLS certificate
- A container registry mirror for air-gapped clusters

The chart bundles Postgres, Valkey and SeaweedFS. Where the client offers managed equivalents, set `deploy: false` for those and point Langfuse at the managed service.

## On the client's AWS (EKS)

EKS for the application and ClickHouse, managed services for everything stateful except ClickHouse. Langfuse maintains an [AWS Terraform module](https://github.com/langfuse/langfuse-terraform-aws) we can start from.

| Resource | S | M | L |
| --- | --- | --- | --- |
| Kubernetes | Amazon EKS | Amazon EKS | Amazon EKS |
| General nodes (EC2) | 3 × `m7i.2xlarge` (8 vCPU, 32 GiB), shared with ClickHouse | 2 × `m7i.2xlarge` | 3 × `m7i.2xlarge` |
| ClickHouse nodes (EC2) | Shared pool | 3 × `m7i.2xlarge` | 3 × `r7i.2xlarge` (8 vCPU, 64 GiB) |
| ClickHouse disks | 3 × 100 GB gp3 | 3 × 300 GB gp3 | 3 × 500 GB gp3 |
| PostgreSQL | RDS for PostgreSQL, `db.t4g.medium`, Single-AZ, 20 GB | RDS, `db.m7g.large`, Multi-AZ, 50 GB | RDS, `db.m7g.large`, Multi-AZ, 50 GB |
| Valkey | ElastiCache for Valkey, `cache.t4g.small` | `cache.t4g.medium` | `cache.m7g.large` + 1 replica |
| Object storage | S3 bucket, \~250 GB used | \~750 GB used | \~1.5 TB used |
| Ingress and TLS | Internal ALB via AWS Load Balancer Controller, ACM certificate | Same | Same |
| DNS | Route 53 private hosted zone | Same | Same |
| Secrets and keys | Secrets Manager, KMS | Same | Same |
| Image mirror | Amazon ECR | Same | Same |

Langfuse's module defaults differ in two places: EKS on Fargate, and Aurora PostgreSQL Serverless v2 at 0.5–2 ACU. Either Postgres option works. ElastiCache needs a parameter group with `maxmemory-policy noeviction`.

## On the client's Azure (AKS)

AKS plus Azure's managed services, following Langfuse's [Azure Terraform module](https://github.com/langfuse/langfuse-terraform-azure) where it sets a default.

| Resource | S | M | L |
| --- | --- | --- | --- |
| Kubernetes | AKS | AKS | AKS |
| General nodes | 3 × `Standard_D8s_v5` (8 vCPU, 32 GiB), shared with ClickHouse | 2 × `Standard_D8s_v5` | 3 × `Standard_D8s_v5` |
| ClickHouse nodes | Shared pool | 3 × `Standard_D8s_v5` | 3 × `Standard_E8s_v5` (8 vCPU, 64 GiB) |
| ClickHouse disks | 3 × 100 GB Premium SSD | 3 × 300 GB Premium SSD | 3 × 500 GB Premium SSD |
| PostgreSQL | Flexible Server, `B_Standard_B2s` (2 vCPU, 4 GiB) | Flexible Server, `GP_Standard_D2s_v3` (2 vCPU, 8 GiB), zone-redundant HA | Same as M |
| Cache | Azure Managed Redis, `Balanced_B3` | Same, with HA | Same, with HA |
| Object storage | Storage account, Blob container, private endpoint, \~250 GB used | \~750 GB used | \~1.5 TB used |
| Ingress and TLS | Application Gateway with WAF, certificate in Key Vault | Same | Same |
| DNS | Private DNS zone | Same | Same |
| Image mirror | Azure Container Registry | Same | Same |

`GP_Standard_D2s_v3` and `Balanced_B3` are the module's defaults; its default AKS node size (`Standard_D2s_v6`) is too small for ClickHouse, so we override it. Set the cache's eviction policy to no eviction.

## On the client's GCP (GKE)

GKE Standard plus Google's managed services, following Langfuse's [GCP Terraform module](https://github.com/langfuse/langfuse-terraform-gcp) where it sets a default.

| Resource | S | M | L |
| --- | --- | --- | --- |
| Kubernetes | GKE Standard | GKE Standard | GKE Standard |
| General nodes | 3 × `n2-standard-8` (8 vCPU, 32 GB), shared with ClickHouse | 2 × `n2-standard-8` | 3 × `n2-standard-8` |
| ClickHouse nodes | Shared pool | 3 × `n2-standard-8` | 3 × `n2-highmem-8` (8 vCPU, 64 GB) |
| ClickHouse disks | 3 × 100 GB pd-balanced | 3 × 300 GB pd-balanced | 3 × 500 GB pd-balanced |
| PostgreSQL | Cloud SQL, `db-custom-2-8192` (2 vCPU, 8 GB), zonal | Same, regional HA | Same, regional HA |
| Cache | Memorystore for Redis, Standard tier (HA), 1 GB | 1 GB | 2 GB |
| Object storage | Cloud Storage bucket, \~250 GB used | \~750 GB used | \~1.5 TB used |
| Ingress and TLS | GKE Gateway or Ingress, Certificate Manager | Same | Same |
| DNS and keys | Cloud DNS private zone, Cloud KMS | Same | Same |
| Image mirror | Artifact Registry | Same | Same |

The module defaults Cloud SQL to `db-perf-optimized-N-2` on Enterprise Plus, which costs more than our load needs; `db-custom-2-8192` on Enterprise is enough. The 1 GB Standard HA cache is the module's default. Set `maxmemory-policy` to `noeviction`.

## Configuration every install must set

These settings go into our bundle so no install depends on someone remembering them.

- [ ] `TELEMETRY_ENABLED=false` on web and worker
- [ ] Images pulled from `docker.io` or the client's mirror, pinned to exact versions
- [ ] Fresh secrets per client: `NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY` (from `openssl rand -hex 32`) and every database password; never reused across clients
- [ ] Open sign-up disabled, SSO through the client's identity provider, first organization, project and API keys created by headless initialization
- [ ] Valkey or managed Redis with `maxmemory-policy noeviction`
- [ ] ClickHouse and Postgres on UTC; ClickHouse system log tables disabled
- [ ] Object storage without bucket versioning; path-style addressing for SeaweedFS; delete permission if we run retention
- [ ] `NODE_OPTIONS=--max-old-space-size` set to match each container's memory
- [ ] LLM connection, if evals are used, pointing only at our own model endpoint

## Sources

- [Langfuse license](https://github.com/langfuse/langfuse/blob/main/LICENSE)
- [Langfuse: Self-hosted pricing](https://langfuse.com/pricing-self-host)
- [Langfuse: Telemetry and hostnames contacted](https://langfuse.com/self-hosting/security/telemetry)
- [Langfuse: Kubernetes (Helm)](https://langfuse.com/self-hosting/deployment/kubernetes-helm)
- [Langfuse Helm chart repository](https://github.com/langfuse/langfuse-k8s)
- [Langfuse: Blob storage](https://langfuse.com/self-hosting/deployment/infrastructure/blobstorage)
- [Langfuse: Redis / Valkey](https://langfuse.com/self-hosting/deployment/infrastructure/cache)
- [Langfuse: Scaling and minimum requirements](https://langfuse.com/self-hosting/configuration/scaling)
- [Langfuse: Docker Compose](https://langfuse.com/self-hosting/deployment/docker-compose)
- [Langfuse Terraform module for AWS](https://github.com/langfuse/langfuse-terraform-aws)
- [Langfuse Terraform module for Azure](https://github.com/langfuse/langfuse-terraform-azure)
- [Langfuse Terraform module for GCP](https://github.com/langfuse/langfuse-terraform-gcp)
- [Langfuse Python SDK](https://github.com/langfuse/langfuse-python)
- [ClickHouse](https://github.com/ClickHouse/ClickHouse) and the [ClickHouse Kubernetes Operator](https://github.com/ClickHouse/clickhouse-operator)
- [PostgreSQL license](https://www.postgresql.org/about/licence/)
- [Valkey](https://github.com/valkey-io/valkey)
- [SeaweedFS](https://github.com/seaweedfs/seaweedfs)
- [cert-manager](https://github.com/cert-manager/cert-manager)
- [Redis licenses](https://redis.io/legal/licenses/)
- [MinIO (Wikipedia)](https://en.wikipedia.org/wiki/MinIO)
- [It's FOSS: MinIO moves away from open source](https://itsfoss.com/news/minio-moves-away-from-open-source/)
- [k3s](https://github.com/k3s-io/k3s)
- [RKE2](https://github.com/rancher/rke2)
- [Longhorn](https://github.com/longhorn/longhorn)

