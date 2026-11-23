import { createFileRoute } from "@tanstack/react-router";
import { AutonomousScreenA } from "@/components/msa/autonomous-screen-a";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      {
        title: "Veteran Access Bridge · Autonomous Scheduling Command Center",
      },
      {
        name: "description",
        content:
          "Synthetic Primary Care voice scheduling Command Center. LiveKit Aura voice scheduling with autonomous operational evidence. Synthetic data only.",
      },
      {
        property: "og:title",
        content: "Veteran Access Bridge · Autonomous Scheduling Command Center",
      },
      {
        property: "og:description",
        content:
          "Primary Care · MCP-Powered. One live synthetic voice call with Avery, governed MCP evidence and after-call tasks.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

function Index() {
  return <AutonomousScreenA />;
}
