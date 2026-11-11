from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait


def execute_dag(plan, invoke, max_workers=3):
    """Execute independent nodes concurrently and pass only declared dependencies."""
    if not 1 <= max_workers <= 3:
        raise ValueError('max_workers must be between 1 and 3')
    remaining = {node.id: node for node in plan.nodes}
    results, pending = {}, {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        while remaining or pending:
            for node_id, node in list(remaining.items()):
                if len(pending) >= max_workers:
                    break
                if all(dep in results for dep in node.depends_on):
                    dependencies = {dep: results[dep] for dep in node.depends_on}
                    pending[pool.submit(invoke, node, dependencies)] = node_id
                    del remaining[node_id]
            if not pending:
                raise ValueError('plan has unresolved dependencies')
            finished, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in finished:
                node_id = pending.pop(future)
                try:
                    results[node_id] = future.result()
                except Exception:
                    for other in pending:
                        other.cancel()
                    raise
    return results
