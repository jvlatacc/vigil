"use agent";

import { useInitialData, useModel, useTool } from "@flue/runtime";
import { ChatIdentity, type ChatIdentityData } from "../chat/identity.ts";
import { internalToolsBridge } from "../config.ts";
import { internalTool } from "../tools/internal.ts";

// The analyst-facing chat, as one agent. Everything durable about it -- the
// transcript, the tool calls, the settlement of each turn -- lives in this
// instance's Durable Object SQLite storage, which is the whole reason for the
// exercise: the conversation outlives the request, the Worker, and the
// deployment, and a reconnect reads the record rather than losing the turn.
//
// The function re-renders before every model call, and each render declares the
// tool set from scratch. So the tools are a function of the identity recorded at
// creation, not of anything the current request carries.
export function Chat(): string {
  // Present in every real render: the schema below is validated before the
  // creating send is admitted, so an instance cannot exist without it. Absent
  // only in a bare tooling render, which is worth an explicit error rather than
  // a set of undefined reads three frames down.
  const identity = useInitialData<ChatIdentityData | undefined>();
  if (identity === undefined) {
    throw new Error("Chat rendered without initial data: identity is recorded at creation, not per request");
  }

  useModel(identity.model);

  // The dispatcher resolved this list against the caller's scopes before it
  // dispatched. That is the authorization decision, made once, on the side that
  // authenticated the human -- re-deriving it here from a request would be
  // deriving it from nothing.
  for (const declaration of identity.tools) {
    useTool(internalTool(declaration, internalToolsBridge));
  }

  return instructionsFor(identity);
}

// Kebab-case and pinned: the durable identity keys the conversation storage and
// names the Durable Object class (FlueChatAgent, migration tag flue-chat), so
// renaming this function must never be a data migration.
Chat.agentName = "chat";
Chat.initialData = ChatIdentity;

// House rules first, then the caller's prompt: the operator-authored persona can
// shape the voice and the emphasis, and cannot quietly widen what the agent is
// allowed to touch.
export function instructionsFor(identity: ChatIdentityData): string {
  const scopes = identity.scopes.length > 0 ? identity.scopes.join(", ") : "none";
  const house = [
    "You are Vigil's security-operations assistant, talking to one analyst about their own environment.",
    `The analyst is ${identity.userId}${identity.tenantId === null ? "" : ` in tenant ${identity.tenantId}`}.`,
    `Their authorization scope is: ${scopes}. The tools you have are the ones that scope allows; there are no others to ask for.`,
    "Ground every claim about the environment in a tool result. Say plainly when a tool returned nothing, was refused, or timed out -- an analyst acting on a gap they think is a finding is the failure this rule exists to prevent.",
    "A tool result carrying capped: true is a truncated answer. Say so rather than reporting the visible rows as the whole set.",
  ].join("\n");

  const lead = identity.systemPrompt.trim();
  return lead === "" ? house : `${house}\n\n${lead}`;
}
