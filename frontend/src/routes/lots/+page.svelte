<script>
  import { untrack } from 'svelte';
  import { fetchDashboard, fetchLots, updateLot } from '$lib/api';
  import PaginationBar from '$lib/PaginationBar.svelte';
  import { maxPageIndex, SEARCH_DEBOUNCE_MS } from '$lib/pagination.js';

  const LOTS_PAGE_SIZE = 15;

  let dashboard = $state(null);
  let lots = $state([]);
  let lotsTotal = $state(0);
  let lotPage = $state(1);
  let searchInput = $state('');
  let searchDebounced = $state('');
  let loading = $state(true);
  let error = $state('');
  /** @type {Record<number, { lot_code: string, unit_price: string }>} */
  let drafts = $state({});
  /** @type {number | null} */
  let savingId = $state(null);
  let loadVersion = 0;
  let listLoading = $state(false);

  $effect(() => {
    searchInput;
    const t = setTimeout(() => {
      searchDebounced = searchInput;
      lotPage = 1;
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  });

  function summaryFor(lotId) {
    return dashboard?.lot_summaries?.find((s) => s.lot_id === lotId) ?? null;
  }

  function normalizeUnitPrice(value) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return '';
    return String(Number(Math.max(0, parsed).toFixed(1)));
  }

  function initDraftsFromLots(list) {
    const next = {};
    for (const lot of list) {
      next[lot.id] = {
        lot_code: lot.lot_code,
        unit_price: String(lot.unit_price),
      };
    }
    drafts = next;
  }

  function patchDraft(lotId, partial) {
    const row = drafts[lotId];
    if (!row) return;
    drafts = { ...drafts, [lotId]: { ...row, ...partial } };
  }

  function handleLotCodeInput(lotId, event) {
    patchDraft(lotId, { lot_code: event.currentTarget.value });
  }

  async function load() {
    const v = ++loadVersion;
    // dashboard を読むと $effect が dashboard に依存し、代入のたびに load が再実行され
    // loadVersion だけが進み finally で loading が下りない。初回判定は依存に含めない。
    const isFirst = untrack(() => dashboard === null);
    if (isFirst) loading = true;
    else listLoading = true;
    error = '';
    try {
      const d = await fetchDashboard();
      const offset = (lotPage - 1) * LOTS_PAGE_SIZE;
      const { items, total } = await fetchLots(d.material.id, {
        limit: LOTS_PAGE_SIZE,
        offset,
        q: searchDebounced.trim() || undefined,
      });
      if (v !== loadVersion) return;
      dashboard = d;
      lots = items;
      lotsTotal = total;
      const cap = maxPageIndex(total, LOTS_PAGE_SIZE);
      if (lotPage > cap) lotPage = cap;
      initDraftsFromLots(items);
    } catch (e) {
      if (v !== loadVersion) return;
      error = e?.message || 'データの取得に失敗しました';
      console.error(e);
    } finally {
      if (v === loadVersion) {
        loading = false;
        listLoading = false;
      }
    }
  }

  $effect(() => {
    lotPage;
    searchDebounced;
    load();
  });

  function handleRowUnitPriceInput(lotId, event) {
    patchDraft(lotId, { unit_price: normalizeUnitPrice(event.currentTarget.value) });
  }

  async function saveLot(lotId) {
    const row = drafts[lotId];
    if (!row || savingId !== null) return;
    const trimmed = row.lot_code.trim();
    if (!trimmed) {
      alert('ロットコードを入力してください');
      return;
    }
    const price = Number(row.unit_price || 0);
    if (!Number.isFinite(price) || price <= 0) {
      alert('単価は0より大きい数値で入力してください');
      return;
    }

    savingId = lotId;
    try {
      await updateLot(lotId, { lot_code: trimmed, unit_price: price });
      await load();
    } catch (e) {
      console.error(e);
      alert(e?.message || '更新に失敗しました');
    } finally {
      savingId = null;
    }
  }

  function formatLotDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('ja-JP', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  }

  function formatSpecNumber(num, maximumFractionDigits = 3) {
    return num?.toLocaleString('ja-JP', { maximumFractionDigits }) ?? '0';
  }
</script>

{#if loading && !dashboard}
  <div class="flex items-center justify-center min-h-[60vh]">
    <span class="material-symbols-outlined text-4xl animate-spin">progress_activity</span>
  </div>
{:else if error && !dashboard}
  <main class="max-w-5xl mx-auto px-8 pt-32 pb-24">
    <div class="rounded-xl border border-error/20 bg-error/10 p-6 text-on-surface">
      <p class="font-semibold text-error mb-2">読み込みに失敗しました</p>
      <p class="text-sm text-on-surface-variant">{error}</p>
      <button
        type="button"
        onclick={load}
        class="mt-4 px-4 py-2 rounded-lg bg-surface-container-high text-on-surface text-sm font-semibold"
      >
        再試行
      </button>
    </div>
  </main>
{:else if dashboard}
  <main class="pt-32 pb-24 px-8 md:px-16 lg:px-32 max-w-5xl mx-auto w-full">
    <section class="mb-10">
      <h2 class="font-headline text-4xl lg:text-5xl font-bold tracking-tight text-on-surface mb-2">情報編集</h2>
    </section>

    <div class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div class="relative w-full max-w-md">
        <span
          class="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant text-sm"
          >search</span
        >
        <input
          type="text"
          bind:value={searchInput}
          placeholder="ロットコードで検索"
          class="w-full rounded-xl border border-outline-variant/15 bg-surface-container-low py-3 pl-12 pr-4 text-sm text-on-surface placeholder:text-outline-variant focus:ring-2 focus:ring-primary/30"
        />
      </div>
      <PaginationBar bind:page={lotPage} total={lotsTotal} pageSize={LOTS_PAGE_SIZE} disabled={listLoading} />
    </div>

    {#if error}
      <div class="mb-6 rounded-xl border border-error/20 bg-error/10 p-4 text-sm text-on-error-container">{error}</div>
    {/if}

    <div class="relative space-y-4 {listLoading ? 'pointer-events-none opacity-50' : ''}">
      {#if listLoading}
        <div class="absolute inset-0 z-10 flex items-start justify-center pt-24">
          <span class="material-symbols-outlined text-3xl animate-spin text-primary">progress_activity</span>
        </div>
      {/if}
      {#each lots as lot (lot.id)}
        {@const summary = summaryFor(lot.id)}
        <div
          class="rounded-2xl border border-outline-variant/15 bg-surface-container-lowest p-6 shadow-sm"
        >
          <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div class="min-w-0 flex-1 space-y-4">
              <div class="flex flex-wrap items-center gap-2 text-sm text-on-surface-variant">
                <span class="rounded-full bg-surface-container-high px-2 py-0.5 text-xs font-medium text-on-surface-variant"
                  >ID {lot.id}</span
                >
                <span>登録 {formatLotDate(lot.created_at)}</span>
              </div>
              <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div class="space-y-2">
                  <label for="lot-code-{lot.id}" class="block font-label text-xs font-semibold uppercase tracking-wider text-on-surface-variant"
                    >ロットコード</label
                  >
                  <input
                    id="lot-code-{lot.id}"
                    type="text"
                    value={drafts[lot.id]?.lot_code ?? ''}
                    oninput={(e) => handleLotCodeInput(lot.id, e)}
                    autocomplete="off"
                    class="w-full rounded-xl border-none bg-surface-container-low py-3 px-4 text-on-surface focus:ring-2 focus:ring-primary/40"
                  />
                </div>
                <div class="space-y-2">
                  <label for="lot-price-{lot.id}" class="block font-label text-xs font-semibold uppercase tracking-wider text-on-surface-variant"
                    >単価（円/kg）</label
                  >
                  <input
                    id="lot-price-{lot.id}"
                    type="number"
                    min="0"
                    step="0.1"
                    value={drafts[lot.id]?.unit_price ?? ''}
                    oninput={(e) => handleRowUnitPriceInput(lot.id, e)}
                    class="no-spinner numeric-input-fluid numeric-input-visible w-full rounded-xl border-none bg-surface-container-low py-3 px-4 text-right tabular-nums text-on-surface focus:ring-2 focus:ring-primary/40"
                  />
                </div>
              </div>
            </div>

            {#if summary}
              <div
                class="grid shrink-0 grid-cols-3 gap-3 rounded-xl bg-surface-container/60 px-4 py-3 text-sm lg:min-w-[14rem]"
              >
                <div>
                  <p class="text-[10px] uppercase tracking-wider text-on-surface-variant">残本</p>
                  <p class="mt-0.5 font-semibold tabular-nums text-on-surface">{formatSpecNumber(summary.current_quantity, 0)}</p>
                </div>
                <div>
                  <p class="text-[10px] uppercase tracking-wider text-on-surface-variant">残重量</p>
                  <p class="mt-0.5 font-semibold tabular-nums text-on-surface">{formatSpecNumber(summary.current_weight, 3)}</p>
                </div>
                <div>
                  <p class="text-[10px] uppercase tracking-wider text-on-surface-variant">在庫金額</p>
                  <p class="mt-0.5 font-semibold tabular-nums text-on-surface">¥{formatSpecNumber(Math.round(summary.current_value), 0)}</p>
                </div>
              </div>
            {/if}
          </div>

          <div class="mt-5 flex justify-end border-t border-outline-variant/10 pt-4">
            <button
              type="button"
              onclick={() => saveLot(lot.id)}
              disabled={savingId !== null}
              class="inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-2.5 text-sm font-semibold text-on-primary transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {#if savingId === lot.id}
                <span class="material-symbols-outlined text-base animate-spin">progress_activity</span>
              {:else}
                <span class="material-symbols-outlined text-base">save</span>
              {/if}
              このロットを保存
            </button>
          </div>
        </div>
      {:else}
        <div class="rounded-2xl border border-dashed border-outline-variant/30 bg-surface-container-low/50 p-12 text-center text-on-surface-variant">
          <p class="font-medium text-on-surface">ロットがまだありません</p>
          <p class="mt-2 text-sm">入庫画面から新規ロットを作成してください。</p>
        </div>
      {/each}
    </div>
  </main>
{/if}
