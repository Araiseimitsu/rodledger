<script>
  let {
    total = 0,
    page = $bindable(1),
    pageSize = 20,
    disabled = false,
    label = '件',
  } = $props();

  const totalPages = $derived(Math.max(1, Math.ceil(total / pageSize)));
  const rangeStart = $derived(total === 0 ? 0 : (page - 1) * pageSize + 1);
  const rangeEnd = $derived(Math.min(page * pageSize, total));

  function goPrev() {
    if (disabled || page <= 1) return;
    page -= 1;
  }

  function goNext() {
    if (disabled || page >= totalPages) return;
    page += 1;
  }
</script>

<div
  class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-outline-variant/15 bg-surface-container-low/50 px-4 py-3 text-sm text-on-surface-variant"
>
  <p class="tabular-nums">
    <span class="font-medium text-on-surface">{rangeStart}</span>
    –
    <span class="font-medium text-on-surface">{rangeEnd}</span>
    / {total.toLocaleString('ja-JP')}
    {label}
  </p>
  <div class="flex items-center gap-2">
    <button
      type="button"
      onclick={goPrev}
      disabled={disabled || page <= 1}
      class="inline-flex min-h-[2.25rem] min-w-[2.25rem] items-center justify-center rounded-lg border border-outline-variant/30 bg-surface text-on-surface transition hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-40"
      aria-label="前のページ"
    >
      <span class="material-symbols-outlined text-lg">chevron_left</span>
    </button>
    <span class="min-w-[5rem] text-center tabular-nums text-on-surface">
      {page} / {totalPages}
    </span>
    <button
      type="button"
      onclick={goNext}
      disabled={disabled || page >= totalPages}
      class="inline-flex min-h-[2.25rem] min-w-[2.25rem] items-center justify-center rounded-lg border border-outline-variant/30 bg-surface text-on-surface transition hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-40"
      aria-label="次のページ"
    >
      <span class="material-symbols-outlined text-lg">chevron_right</span>
    </button>
  </div>
</div>
