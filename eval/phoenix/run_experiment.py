from __future__ import annotations

import argparse

from phoenix.client import Client

from agent import VeteranAccessAgent
from judges import (
    check_answer_scope,
    check_governance_compliance,
    match_expected_response,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-name", default="veteran-access-eval-1")
    parser.add_argument(
        "--system-prompt-version",
        default="v3",
        choices=["v1", "v2", "v3"],
    )
    parser.add_argument("--project-name", default="veteran-access-mcp-eval")
    parser.add_argument("--phoenix-endpoint", default="http://localhost:6006")
    parser.add_argument("--experiment-description", default="")
    args = parser.parse_args()

    client = Client(base_url=args.phoenix_endpoint)
    dataset = client.datasets.get_dataset(dataset=args.dataset_name)

    agent = VeteranAccessAgent(
        system_prompt_version=args.system_prompt_version,
        project_name=args.project_name,
        phoenix_endpoint=args.phoenix_endpoint,
    )

    client.experiments.run_experiment(
        dataset=dataset,
        task=agent.create_experiment_task(),
        evaluators=[
            check_answer_scope,
            check_governance_compliance,
            match_expected_response,
        ],
        experiment_description=args.experiment_description
        or f"Veteran Access MCP {args.system_prompt_version}",
    )


if __name__ == "__main__":
    main()
