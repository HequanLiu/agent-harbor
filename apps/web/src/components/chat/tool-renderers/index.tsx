import type { ToolCallBlock } from '@agentscope-ai/agentscope/message';
import type { ReactNode } from 'react';

import { getResultText, ToolCallRow } from './_shared';
import { BashRenderer } from './BashRenderer';
import {
	defaultGetDisplayName,
	defaultRenderBody,
	defaultRenderConfirmBody,
	defaultRenderHeader,
} from './DefaultRenderer';
import { EditRenderer } from './EditRenderer';
import { GlobRenderer } from './GlobRenderer';
import { GrepRenderer } from './GrepRenderer';
import { MesDraftLink } from './MesDraftLink';
import { ReadRenderer } from './ReadRenderer';
import { TaskCreateRenderer } from './TaskCreateRenderer';
import type { TFunction, ToolCallWithResult, ToolRenderer } from './types';
import { WriteRenderer } from './WriteRenderer';
import { ConnectorApp } from '@/components/connector-ui/ConnectorApp';
import { connectorBinding } from '@/lib/connector-app';
import { mesDraftSnapshot } from '@/lib/mes-draft-link';

const renderers: Record<string, ToolRenderer> = {
	Bash: BashRenderer,
	Read: ReadRenderer,
	Write: WriteRenderer,
	Edit: EditRenderer,
	Glob: GlobRenderer,
	Grep: GrepRenderer,
	TaskCreate: TaskCreateRenderer,
};

function getRenderer(toolName: string): ToolRenderer {
	return renderers[toolName] ?? {};
}

export function getDisplayName(call: ToolCallBlock, t: TFunction): string {
	const r = getRenderer(call.name);
	return r.getDisplayName?.(call, t) ?? defaultGetDisplayName(call);
}

export function renderConfirmBody(call: ToolCallBlock, t: TFunction): ReactNode {
	const r = getRenderer(call.name);
	return r.renderConfirmBody?.(call, t) ?? defaultRenderConfirmBody(call);
}

/**
 * Render a single tool call as one collapsible row. The tool's renderer only
 * supplies the trigger-line `header` and the expandable `body`; the shared
 * `ToolCallRow` owns the collapsible shell, state icon and chevron. Falls back
 * to the `Default*` implementations for tools without a dedicated renderer.
 */
export function renderToolCall(pair: ToolCallWithResult, t: TFunction): ReactNode {
	const r = getRenderer(pair.call.name);
	const header = r.renderHeader?.(pair, t) ?? defaultRenderHeader(pair, t);
	const body = r.renderBody?.(pair, t) ?? defaultRenderBody(pair, t);
	const binding = connectorBinding(pair.result);
	const draft = !binding && mesDraftSnapshot(pair.call.name, getResultText(pair.result), pair.result?.state);
	return <div key={pair.call.id}><ToolCallRow pair={pair} header={header} body={body} />{binding && <ConnectorApp binding={binding} />}{draft && <MesDraftLink key={draft.draft_id} draftId={draft.draft_id} initialDraft={draft} />}</div>;
}
