import { createContext } from 'react';
export const ConnectorChatContext = createContext<{agentId:string|null;sessionId:string|null;busy:boolean;send:(text:string)=>void}|null>(null);
