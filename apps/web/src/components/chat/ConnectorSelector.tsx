import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Loader2, Plug } from "lucide-react";
import { useEffect } from "react";

import { connectorApi } from "@/api/connectors";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useHarbor } from "@/context/HarborContext";

interface Props {
  agentId: string | null;
  sessionId: string | null;
  disabled?: boolean;
  onBusyChange: (busy: boolean) => void;
}

export function ConnectorSelector({
  agentId,
  sessionId,
  disabled,
  onBusyChange,
}: Props) {
  const identity = useHarbor();
  const queryClient = useQueryClient();
  const scope = [identity.active_tenant_id, identity.user.id];
  const connectors = useQuery({
    queryKey: ["connectors", ...scope],
    queryFn: connectorApi.list,
    enabled: Boolean(agentId && sessionId),
    refetchOnWindowFocus: "always",
  });
  const selectionKey = ["session-connectors", ...scope, agentId, sessionId];
  const selection = useQuery({
    queryKey: selectionKey,
    queryFn: () => connectorApi.selection(agentId!, sessionId!),
    enabled: Boolean(agentId && sessionId && connectors.data?.enabled),
    refetchOnWindowFocus: "always",
  });
  const save = useMutation({
    mutationFn: (ids: string[]) =>
      connectorApi.select(agentId!, sessionId!, ids),
    onSuccess: (result) => {
      queryClient.setQueryData(selectionKey, result);
    },
  });
  useEffect(() => {
    onBusyChange(save.isPending);
    return () => onBusyChange(false);
  }, [save.isPending, onBusyChange]);

  const available =
    connectors.data?.items.filter((item) => item.status === "connected") ?? [];
  const selected = (selection.data?.connector_ids ?? []).filter((id) =>
    available.some((item) => item.id === id),
  );
  const pending =
    connectors.isPending || (connectors.data?.enabled && selection.isPending);
  const readError = connectors.error || selection.error;
  const change = (id: string, checked: boolean) => {
    if (save.isPending || disabled || pending || readError) return;
    save.mutate(
      checked ? [...selected, id] : selected.filter((value) => value !== id),
    );
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="secondary"
          size="sm"
          aria-label="连接器"
          disabled={!agentId || !sessionId || disabled}
          title={
            selected.length
              ? available
                  .filter((item) => selected.includes(item.id))
                  .map((item) => item.name)
                  .join("、")
              : "为当前对话选择连接器"
          }
        >
          {save.isPending ? <Loader2 className="animate-spin" /> : <Plug />}
          连接器
          {selected.length > 0 && (
            <span className="rounded bg-background/70 px-1.5 text-xs">
              {selected.length}
            </span>
          )}
          <ChevronDown className="text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        className="min-w-64 max-w-80 font-sans"
      >
        <DropdownMenuLabel>当前对话的连接器</DropdownMenuLabel>
        <p className="px-2 pb-2 text-xs text-muted-foreground">
          可多选，选择后自动用于当前对话。
        </p>
        <DropdownMenuSeparator />
        {pending ? (
          <p role="status" className="p-3 text-sm text-muted-foreground">
            正在读取连接器…
          </p>
        ) : readError ? (
          <div className="p-2">
            <p role="alert" className="text-sm text-destructive">
              {readError.message}
            </p>
            <DropdownMenuItem
              onSelect={(event) => {
                event.preventDefault();
                void connectors.refetch();
                if (connectors.data?.enabled) void selection.refetch();
              }}
            >
              重试
            </DropdownMenuItem>
          </div>
        ) : !connectors.data?.enabled ? (
          <p className="p-3 text-sm text-muted-foreground">
            连接器服务尚未启用。
          </p>
        ) : available.length === 0 ? (
          <p className="p-3 text-sm text-muted-foreground">
            暂无已连接的连接器，请先在连接器页面完成授权。
          </p>
        ) : (
          available.map((item) => (
            <DropdownMenuCheckboxItem
              key={item.id}
              checked={selected.includes(item.id)}
              disabled={save.isPending || disabled}
              onSelect={(event) => event.preventDefault()}
              onCheckedChange={(checked) => change(item.id, checked === true)}
            >
              <span className="truncate">{item.name}</span>
            </DropdownMenuCheckboxItem>
          ))
        )}
        {save.isPending && (
          <p role="status" className="px-2 py-1 text-xs text-muted-foreground">
            正在保存…
          </p>
        )}
        {save.error && (
          <p role="alert" className="px-2 py-2 text-sm text-destructive">
            {save.error.message}
          </p>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
