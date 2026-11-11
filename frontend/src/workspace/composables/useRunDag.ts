
import { onBeforeUnmount, ref, watch, type Ref } from 'vue';
import { workspaceEventsUrl, workspaceRequest, WorkspaceRequestError, type DagSnapshot } from '../api';

const events = ['queued', 'planning', 'running', 'node_started', 'node_attempt', 'node_retry',
  'node_succeeded', 'node_failed', 'node_skipped', 'node_cancelled', 'node_result_discarded',
  'completed', 'failed', 'cancelled', 'cancel_requested', 'waiting_review', 'review_approved', 'update'];
const terminal = new Set(['completed', 'failed', 'cancelled']);

export function useRunDag(workspaceId: Ref<string>, runId: Ref<string>, active: Ref<boolean>) {
  const graph = ref<DagSnapshot | null>(null);
  const loading = ref(false), disconnected = ref(false), error = ref('');
  let source: EventSource | null = null, generation = 0, cursor = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let authorizationTimer: ReturnType<typeof setTimeout> | undefined;
  let refreshInFlight = false, refreshPending = false;

  function close() {
    source?.close(); source = null;
    if (timer) clearTimeout(timer);
    if (authorizationTimer) clearTimeout(authorizationTimer);
    timer = undefined; authorizationTimer = undefined;
  }
  function deny(message: string, notifyWorkspace = true) {
    close(); graph.value = null; error.value = message; disconnected.value = false;
    if (notifyWorkspace) window.dispatchEvent(new CustomEvent('inquiry-workspace:access-denied', {detail: {path: '/' + workspaceId.value + '/runs/' + runId.value}}));
  }
  async function refresh(epoch = generation) {
    if (!workspaceId.value || !runId.value || !active.value || epoch !== generation) return;
    if (refreshInFlight) { refreshPending = true; return; }
    refreshInFlight = true;
    try {
      const snapshot = await workspaceRequest<DagSnapshot>(
        '/' + encodeURIComponent(workspaceId.value) + '/runs/' + encodeURIComponent(runId.value) + '/graph');
      if (epoch !== generation) return;
      if (snapshot.event_cursor >= cursor) {
        graph.value = snapshot;
        cursor = snapshot.event_cursor;
        error.value = '';
        if (terminal.has(snapshot.status)) {
          close(); disconnected.value = false;
          authorizationTimer = setTimeout(() => void refresh(epoch), 15000);
        }
      } else {
        refreshPending = true;
      }
    } catch (e) {
      if (epoch !== generation) return;
      if (e instanceof WorkspaceRequestError && [401, 403, 404].includes(e.status)) {
        deny('运行或课程依据的访问权限已失效，请重新检查权限。', e.status !== 404);
      } else if (!(e instanceof WorkspaceRequestError && e.status === 409)) {
        const wasTerminal = !!graph.value && terminal.has(graph.value.status);
        error.value = '暂时无法验证运行权限，正在重试。';
        if (wasTerminal) {
          graph.value = null;
          authorizationTimer = setTimeout(() => void refresh(epoch), 3000);
        } else if (!source) {
          timer = setTimeout(() => void resync(epoch), 3000);
        }
      } else {
        refreshPending = true;
      }
    } finally {
      refreshInFlight = false;
      if (epoch === generation) {
        loading.value = false;
        if (refreshPending) {
          refreshPending = false;
          timer = setTimeout(() => void refresh(epoch), 200);
        }
      }
    }
  }
  function scheduleRefresh(epoch: number) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => void refresh(epoch), 120);
  }
  function connect(epoch: number) {
    if (!graph.value || terminal.has(graph.value.status) || epoch !== generation) return;
    source?.close();
    source = new EventSource(workspaceEventsUrl(workspaceId.value, runId.value, cursor), {withCredentials: true});
    source.onopen = () => { if (epoch === generation) disconnected.value = false; };
    source.onerror = () => {
      if (epoch !== generation) return;
      disconnected.value = true;
      scheduleRefresh(epoch);
    };
    source.addEventListener('access_revoked', () => {
      if (epoch === generation) deny('运行或课程依据的访问权限已失效，请重新检查权限。');
    });
    const receive = (event: Event) => {
      if (epoch !== generation) return;
      const id = Number((event as MessageEvent).lastEventId);
      if (!Number.isSafeInteger(id) || id <= 0 || id <= cursor) return;
      if (id !== cursor + 1) {
        close(); disconnected.value = true;
        void resync(epoch);
        return;
      }
      cursor = id;
      scheduleRefresh(epoch);
    };
    for (const event of events) source.addEventListener(event, receive);
  }
  async function resync(epoch: number) {
    await refresh(epoch);
    if (epoch === generation && !error.value && graph.value && active.value && !terminal.has(graph.value.status)) connect(epoch);
  }
  watch([workspaceId, runId, active], async () => {
    const epoch = ++generation;
    close(); cursor = 0; graph.value = null; error.value = ''; disconnected.value = false;
    refreshPending = false; refreshInFlight = false;
    if (!workspaceId.value || !runId.value || !active.value) { loading.value = false; return; }
    loading.value = true;
    await resync(epoch);
  }, {immediate: true});
  onBeforeUnmount(() => { generation++; close(); });
  return { graph, loading, disconnected, error, refresh: () => void resync(generation) };
}

