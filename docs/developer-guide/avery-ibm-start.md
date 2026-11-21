# Build your own Avery voice scheduling experience

!!! info "Your editor is a choice, not a cloud dependency"
    Develop from local VS Code (recommended) or GitHub Codespaces (optional). This chapter provisions external services for the full Avery experience; Codespaces is not required. See [Why we chose this architecture](engineering-decisions.md) and [Configuration and secrets](configuration-and-secrets.md).

!!! warning "Keep IBM account credentials separate from runtime secrets"
    IBM Cloud SSO, Orchestrate CLI activation, API credentials and Code Engine secrets serve different purposes. A successful login does not automatically configure the deployed application.


Start here to run Avery in your own cloud environment. Once the full setup is complete, you can select **Call in Browser**, speak with Avery, choose a test appointment and inspect the booking receipt. After you hang up, you can check the CRM note and confirmation letter.

**Your IBM setup is ready when** you can select your Code Engine project and list agents in your own watsonx Orchestrate workspace. Follow [Set up IBM from your terminal](#set-up-ibm-from-your-terminal) for copyable commands. If you prefer the console, start with [your existing account](#i-already-have-ibm-cloud) or [a new account](#im-starting-from-scratch).

| IBM term | What it means here |
|---|---|
| **Account** | The account that owns the services and receives any charges. Your IBM login may give you access to several accounts. |
| **Resource group** | A named group inside an account for organizing resources and controlling access. Use the group assigned to your project. |
| **watsonx Orchestrate instance** | Your team's workspace for configuring Avery's instructions and attaching MCP tools. |
| **Code Engine project** | The place where you will deploy the scheduling backend and voice worker. An empty project is sufficient today. |

## I already have IBM Cloud

**Using the CLI?** [Sign in and find your existing resources](#set-up-ibm-from-your-terminal). You can skip both creation commands when the resources already exist.

1. Sign in to the [IBM Cloud resource list](https://cloud.ibm.com/resources). Check the account selector at the top, especially if you use both personal and organization accounts.
2. Find your team's **watsonx Orchestrate** service. An instance may have a custom name. Open its details, note the instance name and region, and use the launch action to open Orchestrate. **Success:** you can enter the Orchestrate workspace. A newly provisioned workspace can be empty.
3. In a second tab, open [Code Engine → Projects](https://cloud.ibm.com/codeengine/projects). Open your intended project and check its name, location, resource group and status. **Success:** the project is **Active**.
4. If both resources are available, go straight to [Record your IBM setup](#record-your-ibm-setup). If one is missing, follow just its creation step below. If you expect to see an existing team resource, first check the account, filters and permissions with its owner.

## I’m starting from scratch

**Using the CLI?** Complete account registration below, then follow [the terminal walkthrough](#set-up-ibm-from-your-terminal), including the creation steps for the resources you need.

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

## Set up IBM from your terminal

Use a **Bash** terminal for these blocks. In GitHub Codespaces choose **Terminal → New Terminal**. On Windows, open a **WSL** window in VS Code and use its Linux terminal. Run the blocks in order in the same terminal so the names you enter carry forward. You need an IBM Cloud account and permission to use the intended resource group.

### 1. Install the two command-line tools

`ibmcloud` manages the cloud account and hosting project. `orchestrate` connects to the agent workspace. On Linux, including Codespaces and WSL, these commands download IBM’s installer to a file and run it. If `ibmcloud version` already works, skip the download and install commands. [IBM Cloud CLI installation](https://cloud.ibm.com/docs/cli?topic=cli-getting-started)

```bash
curl --fail --show-error --location https://clis.cloud.ibm.com/install/linux -o /tmp/avery-ibmcloud-install.sh
sh /tmp/avery-ibmcloud-install.sh
ibmcloud version
ibmcloud plugin install code-engine
ibmcloud ce --help
```

**Check:** the first check prints the IBM CLI version and the last lists Code Engine commands. Next install IBM’s agent development kit in its own Python environment. If `uv --version` fails, first follow the [uv installation steps](https://docs.astral.sh/uv/getting-started/installation/) and reopen the terminal.

```bash
uv venv --python 3.12 "$HOME/.venvs/avery-orchestrate"
source "$HOME/.venvs/avery-orchestrate/bin/activate"
uv pip install ibm-watsonx-orchestrate
orchestrate --help
```

**Check:** the help includes the `env` and `agents` commands. When returning in a new terminal, run the `source` line again.

### 2. Sign in and choose where Avery will run

```bash
ibmcloud login --sso
ibmcloud resource groups
ibmcloud regions
```

Open the sign-in link IBM prints, complete sign-in and enter the one-time code at the terminal prompt. Select the account that owns your project. Copy your resource group name from the first list and your intended Code Engine region from the second. For example, the original demo used `ca-tor` for hosting. Type your own values when prompted.

```bash
read -rp "Resource group name: " GROUP_NAME
read -rp "Code Engine region: " CE_REGION
ibmcloud target -r "$CE_REGION" -g "$GROUP_NAME"
ibmcloud target
ibmcloud resource service-instances -g "$GROUP_NAME"
ibmcloud ce project list
```

**Check:** confirm the account, region and resource group in the target output. Look for your Orchestrate instance in the service list and your hosting project in the project list. If an expected project is missing, check its region and group before creating another.

### 3. Find or create the Orchestrate instance

**Existing instance:** enter its exact name and inspect its details. Then go to step 4.

```bash
read -rp "Existing Orchestrate instance name: " WXO_NAME
ibmcloud resource service-instance "$WXO_NAME"
```

**New instance only:** inspect the plans and available locations. Check the plan price and your account entitlement in the [Orchestrate catalog](https://cloud.ibm.com/catalog/services/watsonx-orchestrate) before creating it. The Orchestrate region can differ from the hosting region.

```bash
ibmcloud catalog service watsonx-orchestrate
read -rp "New Orchestrate instance name: " WXO_NAME
read -rp "Approved service plan name or ID from the catalog: " WXO_PLAN
read -rp "Location offered for that plan: " WXO_REGION
```

Run the following when ready to provision that plan. If your organization supplies an instance or requires a subscription, use its provisioning instructions. [IBM service creation command reference](https://cloud.ibm.com/docs/cli?topic=cli-ibmcloud_commands_resource)

```bash
ibmcloud resource service-instance-create "$WXO_NAME" watsonx-orchestrate "$WXO_PLAN" "$WXO_REGION" -g "$GROUP_NAME"
ibmcloud resource service-instance "$WXO_NAME"
```

**Check:** IBM shows the intended instance, its location and its state. If it is provisioning, repeat only the details command until it is active.

### 4. Select the Code Engine project

```bash
read -rp "Code Engine project name (existing or new): " CE_PROJECT
```

If you found the project in step 2, go directly to the selection block. **For a new project only**, run:

```bash
ibmcloud ce project create --name "$CE_PROJECT"
```

Select the project and check the result. [IBM Code Engine project instructions](https://cloud.ibm.com/docs/codeengine?topic=codeengine-manage-project)

```bash
ibmcloud ce project select --name "$CE_PROJECT"
ibmcloud ce project get --name "$CE_PROJECT"
```

**Check:** the project details show your project name, region and an active state.

### 5. Connect the Orchestrate CLI and prove it can reach the workspace

Launch your instance from the [IBM Cloud resource list](https://cloud.ibm.com/resources). In Orchestrate, open **Profile → Settings → API details**. Copy the **Service instance URL** and obtain an authorized IBM Cloud API key for this instance. Use the URL shown there, including its instance identifier. Keep the key private for the activation prompt. [IBM’s Orchestrate CLI setup walkthrough](https://ibm.github.io/EEL-agentic-ai-bootcamp/labs/environment-setup-lab/wxo-client-setup/)

```bash
orchestrate env list
read -rp "Local name for this Orchestrate connection: " WXO_ENV
```

Choose a memorable local name such as `avery-review`. If an entry already points to your instance, enter that entry’s name above and skip the following registration block.

```bash
read -rp "Orchestrate service instance URL: " WXO_URL
orchestrate env add --name "$WXO_ENV" --url "$WXO_URL" --type ibm_iam
```

```bash
orchestrate env activate "$WXO_ENV"
orchestrate agents list
orchestrate toolkits list
```

**Check:** enter the key when prompted. Both list commands should return successfully. A new workspace may have no custom agents or toolkits yet. If the token expires, repeat the activation command. If activation succeeds but listing is forbidden, have the instance owner check your access to that specific workspace.

Both IBM connections are ready. If you started with IBM, complete [the test database](supabase.md) and [VA access](vha-sandbox.md) before attempting the connected call.

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

**Continue with [Connect Avery and the MCP toolkit](avery-agent.md).**
