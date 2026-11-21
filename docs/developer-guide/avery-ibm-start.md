# Build your own Avery voice scheduling experience

Start here to run Avery in your own cloud environment. Once the full setup is complete, you can select **Call in Browser**, speak with Avery, choose a test appointment and inspect the booking receipt. After you hang up, you can check the CRM note and confirmation letter.

**Today's checkpoint:** Open two browser tabs in your IBM Cloud account. One should show your watsonx Orchestrate workspace. The other should show an active Code Engine project. A browser and your IBM login are enough for this step.

| IBM term | What it means here |
|---|---|
| **Account** | The account that owns the services and receives any charges. Your IBM login may give you access to several accounts. |
| **Resource group** | A named group inside an account for organizing resources and controlling access. Use the group assigned to your project. |
| **watsonx Orchestrate instance** | Your team's workspace for configuring Avery's instructions and attaching MCP tools. |
| **Code Engine project** | The place where you will deploy the scheduling backend and voice worker. An empty project is sufficient today. |

## I already have IBM Cloud

1. Sign in to the [IBM Cloud resource list](https://cloud.ibm.com/resources). Check the account selector at the top, especially if you use both personal and organization accounts.
2. Find your team's **watsonx Orchestrate** service. An instance may have a custom name. Open its details, note the instance name and region, and use the launch action to open Orchestrate. **Success:** you can enter the Orchestrate workspace. A newly provisioned workspace can be empty.
3. In a second tab, open [Code Engine → Projects](https://cloud.ibm.com/codeengine/projects). Open your intended project and check its name, location, resource group and status. **Success:** the project is **Active**.
4. If both resources are available, go straight to [Record your IBM setup](#record-your-ibm-setup). If one is missing, follow just its creation step below. If you expect to see an existing team resource, first check the account, filters and permissions with its owner.

## I’m starting from scratch

### 1. Get into the right IBM Cloud account

If your organization or event supplies an account, accept its invitation and select that account after signing in. Otherwise open [IBM Cloud registration](https://cloud.ibm.com/registration), follow the account and email verification prompts, and sign in. **Before accepting a billing step**, check whose account will own these services and what spending the owner has approved. The original demonstration used a hackathon account. Your account's plans and entitlements may differ.

### 2. Create the Orchestrate workspace

1. Open the [watsonx Orchestrate service in IBM's catalog](https://cloud.ibm.com/catalog/services/watsonx-orchestrate) while signed in.
2. Choose an available location and review **Pricing plans**. If your account offers a trial, check its duration and terms. If only a paid plan is available, decide whether to accept its displayed charges before selecting **Create**.
3. Choose the approved plan, enter a recognizable instance name, such as **avery-orchestrate**, and select your resource group. Review the selections and create the instance.
4. Return to the [resource list](https://cloud.ibm.com/resources), open the new instance and launch Orchestrate. Keep the workspace tab open. If creation is unavailable in a shared account, ask the account owner which existing instance or provisioning permissions to use.

### 3. Create the Code Engine project

1. Open [Code Engine → Projects](https://cloud.ibm.com/codeengine/projects) and select **Create**. Choose a location available to your account. Record it for later deployment commands.
2. Enter a unique project name, such as **avery-scheduling-review**, and select your resource group. If IBM reports the name is taken, choose another name.
3. Review [Code Engine pricing](https://cloud.ibm.com/docs/codeengine?topic=codeengine-pricing) before deploying workloads. Select **Create** and wait for the project to become **Active**. Leave the project overview open. [IBM's project creation instructions](https://cloud.ibm.com/docs/codeengine?topic=codeengine-manage-project)

## Record your IBM setup

Keep the following in your own setup notes. You will use these labels again when you configure the agent and deploy the backend.

| Record | Where to find it |
|---|---|
| IBM account and resource group | Account selector and resource details |
| Orchestrate instance name and region | Orchestrate service instance details |
| Code Engine project name and region | Code Engine project overview |

**You’re ready for the next step when** you can reopen your Orchestrate workspace and identify the active Code Engine project in your own account. Use your own names in later commands. Names such as `veteran-access-dev` in historical runbooks refer to the original team's environment.

## Where this fits in the full setup

| Next step | What you will verify |
|---|---|
| **Prepare Supabase** | The test database contains a case and appointment slots, and the backend can read them. |
| **Connect VA sandbox reads** | The facility lookup identifies VA as its data source. Patient-record reads need their own authorized access. |
| **Deploy the backend and connect Avery** | Configure your own agent and attach the authorized tools. When the backend has your Orchestrate connection details, switch its example setting `ORCHESTRATE_RUNTIME_MODE=fake` to `remote`. Verify an agent-selected tool call against the backend trace. |
| **Connect LiveKit, Deepgram and the browser app** | A browser caller and the voice worker join the same session, and speech works in both directions. |
| **Complete a test appointment** | Verify identity, choose a time, confirm, and inspect the persisted receipt. End the call and check the CRM note and letter. |

**Continue with [Prepare the Supabase test database](supabase.md).** For the complete set of service connections, see [the connected-product guide](connected-product.md#reproduce-the-connected-voice-product).
