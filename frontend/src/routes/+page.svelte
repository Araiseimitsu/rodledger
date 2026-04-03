<script>
  import { onMount } from 'svelte';
  import { fetchDashboard, fetchLots, fetchLotSummariesPage, fetchTransactions, updateLot, updateMaterial } from '$lib/api';
  import PaginationBar from '$lib/PaginationBar.svelte';
  import { maxPageIndex, SEARCH_DEBOUNCE_MS } from '$lib/pagination.js';

  const LOT_PAGE_SIZE = 10;
  const RECENT_PAGE_SIZE = 5;

  let dashboard = $state(null);
  let currentLot = $state(null);
  let loading = $state(true);
  let loadError = $state(null);
  let saveError = $state(null);
  let saveMessage = $state(null);
  let saving = $state(false);
  let showEditor = $state(false);
  let form = $state({
    diameter: '',
    length: '',
    density: '',
    unit_price: '',
  });

  let lotSummariesPage = $state([]);
  let lotSummariesTotal = $state(0);
  let lotPage = $state(1);
  let lotSearchInput = $state('');
  let lotSearchDebounced = $state('');
  let lotListLoading = $state(false);

  let recentItems = $state([]);
  let recentTotal = $state(0);
  let recentPage = $state(1);
  let recentSearchInput = $state('');
  let recentSearchDebounced = $state('');
  let recentLoading = $state(false);

  let lotLoadVersion = 0;
  let recentLoadVersion = 0;

  onMount(async () => {
    await loadDashboard();
  });

  $effect(() => {
    lotSearchInput;
    const t = setTimeout(() => {
      lotSearchDebounced = lotSearchInput;
      lotPage = 1;
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  });

  $effect(() => {
    recentSearchInput;
    const t = setTimeout(() => {
      recentSearchDebounced = recentSearchInput;
      recentPage = 1;
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  });

  async function loadLotSummariesSection() {
    if (!dashboard?.material?.id) return;
    const v = ++lotLoadVersion;
    lotListLoading = true;
    try {
      const offset = (lotPage - 1) * LOT_PAGE_SIZE;
      const { items, total } = await fetchLotSummariesPage(dashboard.material.id, {
        limit: LOT_PAGE_SIZE,
        offset,
        q: lotSearchDebounced.trim() || undefined,
        nonzero_only: true,
      });
      if (v !== lotLoadVersion) return;
      lotSummariesPage = items;
      lotSummariesTotal = total;
      const cap = maxPageIndex(total, LOT_PAGE_SIZE);
      if (lotPage > cap) lotPage = cap;
    } catch (e) {
      console.error(e);
    } finally {
      if (v === lotLoadVersion) lotListLoading = false;
    }
  }

  async function loadRecentSection() {
    if (!dashboard?.material?.id) return;
    const v = ++recentLoadVersion;
    recentLoading = true;
    try {
      const offset = (recentPage - 1) * RECENT_PAGE_SIZE;
      const { items, total } = await fetchTransactions({
        material_id: dashboard.material.id,
        limit: RECENT_PAGE_SIZE,
        offset,
        q: recentSearchDebounced.trim() || undefined,
      });
      if (v !== recentLoadVersion) return;
      recentItems = items;
      recentTotal = total;
      const cap = maxPageIndex(total, RECENT_PAGE_SIZE);
      if (recentPage > cap) recentPage = cap;
    } catch (e) {
      console.error(e);
    } finally {
      if (v === recentLoadVersion) recentLoading = false;
    }
  }

  $effect(() => {
    dashboard?.material?.id;
    lotPage;
    lotSearchDebounced;
    loadLotSummariesSection();
  });

  $effect(() => {
    dashboard?.material?.id;
    recentPage;
    recentSearchDebounced;
    loadRecentSection();
  });

  async function loadDashboard(showLoader = true) {
    if (showLoader) loading = true;
    loadError = null;

    try {
      const nextDashboard = await fetchDashboard();
      const { items: lots } = await fetchLots(nextDashboard.material.id);

      dashboard = nextDashboard;
      currentLot = lots[0] ?? null;
      syncForm(nextDashboard, currentLot);
    } catch (e) {
      loadError = e.message;
    } finally {
      if (showLoader) loading = false;
    }
  }

  function syncForm(nextDashboard, lot) {
    form = {
      diameter: String(nextDashboard.material.diameter ?? ''),
      length: String(nextDashboard.material.length ?? ''),
      density: String(nextDashboard.material.density ?? ''),
      unit_price: String(lot?.unit_price ?? ''),
    };
  }

  function openEditor() {
    saveError = null;
    saveMessage = null;
    showEditor = true;
    syncForm(dashboard, currentLot);
  }

  function cancelEditor() {
    saveError = null;
    saveMessage = null;
    showEditor = false;
    syncForm(dashboard, currentLot);
  }

  function parsePositiveNumber(label, value) {
    const parsed = Number.parseFloat(value);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      throw new Error(`${label}は0より大きい数値で入力してください`);
    }
    return parsed;
  }

  async function saveMaterialSettings() {
    if (!dashboard?.material) return;

    saveError = null;
    saveMessage = null;
    saving = true;

    try {
      const diameter = parsePositiveNumber('径', form.diameter);
      const length = parsePositiveNumber('長さ基本', form.length);
      const density = parsePositiveNumber('比重', form.density);
      const unitPrice = parsePositiveNumber('単価', form.unit_price);

      const requests = [
        updateMaterial(dashboard.material.id, {
          diameter,
          length,
          density,
        }),
      ];

      if (currentLot) {
        requests.push(updateLot(currentLot.id, { unit_price: unitPrice }));
      } else {
        throw new Error('単価を更新するロットが見つかりません');
      }

      await Promise.all(requests);
      await loadDashboard(false);
      showEditor = false;
      saveMessage = '材料設定を更新しました';
    } catch (e) {
      saveError = e.message;
    } finally {
      saving = false;
    }
  }

  function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('ja-JP', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  function getTypeIcon(type) {
    const icons = {
      in: 'south_west',
      out: 'north_east',
      return: 'assignment_return',
      adjust: 'tune',
    };
    return icons[type] || 'swap_horiz';
  }

  function getTypeColor(type) {
    const colors = {
      in: 'text-primary',
      out: 'text-error',
      return: 'text-secondary',
      adjust: 'text-tertiary',
    };
    return colors[type] || 'text-on-surface';
  }

  function formatNumber(num) {
    return num?.toLocaleString('ja-JP') ?? '0';
  }

  function formatSpecNumber(num, maximumFractionDigits = 3) {
    return num?.toLocaleString('ja-JP', { maximumFractionDigits }) ?? '0';
  }

</script>

{#if loading}
  <div class="flex items-center justify-center min-h-[60vh]">
    <span class="material-symbols-outlined text-4xl animate-spin">progress_activity</span>
  </div>
{:else if loadError}
  <div class="max-w-5xl mx-auto px-8 py-16">
    <div class="bg-error-container/20 rounded-xl p-6 text-on-error-container">
      <p>エラー: {loadError}</p>
    </div>
  </div>
{:else if dashboard}
  <div class="max-w-7xl mx-auto px-8 mt-16 pb-32">
    <!-- Hero Header -->
    <section class="mb-16">
      <h2 class="font-headline text-5xl md:text-6xl text-on-surface mb-4">The Lucid Archive</h2>
    </section>

    {#if saveError}
      <div class="mb-6 rounded-xl border border-error/20 bg-error-container/40 px-5 py-4 text-sm text-on-error-container">
        {saveError}
      </div>
    {/if}

    {#if saveMessage}
      <div class="mb-6 rounded-xl border border-primary/20 bg-primary-container/40 px-5 py-4 text-sm text-on-primary-container">
        {saveMessage}
      </div>
    {/if}

    <!-- Material Card Grid -->
    <div class="grid grid-cols-1 md:grid-cols-12 gap-6">
      <!-- Material Specification -->
      <div class="md:col-span-8 bg-surface-container-lowest border border-outline-variant/15 rounded-xl p-10 relative overflow-hidden">
        <div class="relative z-10">
          <div class="mb-4 flex flex-wrap items-start justify-between gap-4">
            <span class="text-xs font-label uppercase tracking-widest text-primary font-bold block">材料情報</span>
            {#if !showEditor}
              <button
                type="button"
                class="rounded-lg border border-outline-variant/30 bg-surface px-4 py-2 text-sm font-medium text-on-surface transition hover:bg-surface-container"
                onclick={openEditor}
              >
                条件を編集
              </button>
            {/if}
          </div>
          <h3 class="font-headline text-4xl text-on-surface mb-2">{dashboard.material.name} Steel Rods</h3>
          <div class="flex flex-wrap gap-4 mt-6">
            <div class="bg-surface-container px-4 py-2 rounded-lg">
              <p class="text-[10px] text-on-surface-variant uppercase tracking-tighter">直径</p>
              <p class="font-body font-bold text-lg">{formatSpecNumber(dashboard.material.diameter, 2)} mm</p>
            </div>
            <div class="bg-surface-container px-4 py-2 rounded-lg">
              <p class="text-[10px] text-on-surface-variant uppercase tracking-tighter">長さ</p>
              <p class="font-body font-bold text-lg">{formatSpecNumber(dashboard.material.length, 1)} mm</p>
            </div>
            <div class="bg-surface-container px-4 py-2 rounded-lg">
              <p class="text-[10px] text-on-surface-variant uppercase tracking-tighter">比重</p>
              <p class="font-body font-bold text-lg">{formatSpecNumber(dashboard.material.density, 3)}</p>
            </div>
            <div class="bg-surface-container px-4 py-2 rounded-lg">
              <p class="text-[10px] text-on-surface-variant uppercase tracking-tighter">単価</p>
              <p class="font-body font-bold text-lg">¥{formatSpecNumber(currentLot?.unit_price, 1)}/kg</p>
            </div>
            <div class="bg-surface-container px-4 py-2 rounded-lg">
              <p class="text-[10px] text-on-surface-variant uppercase tracking-tighter">単重</p>
              <p class="font-body font-bold text-lg">{formatSpecNumber(dashboard.material.weight_per_unit, 3)} kg/本</p>
            </div>
          </div>

          {#if showEditor}
            <div class="mt-8 rounded-2xl border border-outline-variant/20 bg-surface/90 p-6 backdrop-blur">
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <label class="block">
                  <span class="mb-2 block text-xs font-label uppercase tracking-widest text-on-surface-variant">単価 円/kg</span>
                  <input bind:value={form.unit_price} class="w-full rounded-lg border border-outline-variant/30 bg-surface-container px-4 py-3 text-on-surface outline-none transition focus:border-primary" inputmode="decimal" />
                </label>
                <label class="block">
                  <span class="mb-2 block text-xs font-label uppercase tracking-widest text-on-surface-variant">比重</span>
                  <input bind:value={form.density} class="w-full rounded-lg border border-outline-variant/30 bg-surface-container px-4 py-3 text-on-surface outline-none transition focus:border-primary" inputmode="decimal" />
                </label>
                <label class="block">
                  <span class="mb-2 block text-xs font-label uppercase tracking-widest text-on-surface-variant">長さ基本 mm</span>
                  <input bind:value={form.length} class="w-full rounded-lg border border-outline-variant/30 bg-surface-container px-4 py-3 text-on-surface outline-none transition focus:border-primary" inputmode="decimal" />
                </label>
                <label class="block">
                  <span class="mb-2 block text-xs font-label uppercase tracking-widest text-on-surface-variant">径 mm</span>
                  <input bind:value={form.diameter} class="w-full rounded-lg border border-outline-variant/30 bg-surface-container px-4 py-3 text-on-surface outline-none transition focus:border-primary" inputmode="decimal" />
                </label>
              </div>

              <div class="mt-6 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  class="rounded-lg bg-primary px-5 py-3 text-sm font-medium text-on-primary transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                  onclick={saveMaterialSettings}
                  disabled={saving}
                >
                  {#if saving}保存中...{:else}保存する{/if}
                </button>
                <button
                  type="button"
                  class="rounded-lg border border-outline-variant/30 px-5 py-3 text-sm font-medium text-on-surface transition hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-60"
                  onclick={cancelEditor}
                  disabled={saving}
                >
                  キャンセル
                </button>
              </div>
            </div>
          {/if}
        </div>
        <div class="absolute -right-16 -bottom-16 opacity-5 pointer-events-none">
          <span class="material-symbols-outlined text-[320px]">precision_manufacturing</span>
        </div>
      </div>

      <!-- Total Value -->
      <div class="md:col-span-4 bg-surface-container-low rounded-xl p-8 flex flex-col justify-center">
        <span class="text-xs font-label uppercase tracking-widest text-on-surface-variant mb-2">在庫金額</span>
        <div class="flex items-baseline gap-2">
          <span class="text-on-surface text-4xl font-headline italic">¥</span>
          <span class="text-on-surface text-6xl font-headline">{formatNumber(Math.round(dashboard.total_value))}</span>
        </div>
      </div>

      <!-- Weight -->
      <div class="md:col-span-6 bg-surface-container-lowest border border-outline-variant/15 rounded-xl p-8 hover:bg-surface-container-low transition-colors duration-500">
        <div class="w-10 h-10 rounded-full bg-primary-container flex items-center justify-center mb-6">
          <span class="material-symbols-outlined text-on-primary-container">weight</span>
        </div>
        <p class="text-on-surface-variant text-sm font-label mb-1">現在重量</p>
        <div class="flex items-baseline gap-2">
          <span class="text-5xl font-headline text-on-surface">{formatNumber(dashboard.total_weight.toFixed(1))}</span>
          <span class="text-xl font-label text-on-surface-variant">kg</span>
        </div>
      </div>

      <!-- Quantity -->
      <div class="md:col-span-6 bg-surface-container-lowest border border-outline-variant/15 rounded-xl p-8 hover:bg-surface-container-low transition-colors duration-500">
        <div class="w-10 h-10 rounded-full bg-secondary-container flex items-center justify-center mb-6">
          <span class="material-symbols-outlined text-on-secondary-container">reorder</span>
        </div>
        <p class="text-on-surface-variant text-sm font-label mb-1">現在本数</p>
        <div class="flex items-baseline gap-2">
          <span class="text-5xl font-headline text-on-surface">{formatNumber(dashboard.total_effective_quantity ?? dashboard.total_quantity)}</span>
          <span class="text-xl font-label text-on-surface-variant">本</span>
        </div>
      </div>

    </div>

    <section class="mt-12 rounded-3xl border border-outline-variant/15 bg-surface-container-lowest p-8 md:p-10">
      <div class="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h3 class="font-headline text-2xl text-on-surface">ロット別在庫</h3>
          <a href="/lots" class="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline">
            <span class="material-symbols-outlined text-base">edit_square</span>
            ロットコード・単価の修正
          </a>
        </div>
        <p class="text-sm text-on-surface-variant">
          合計 {formatNumber(dashboard.total_effective_quantity ?? dashboard.total_quantity)} 本 / {formatSpecNumber(dashboard.total_weight, 3)} kg
        </p>
      </div>

      <div class="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div class="relative w-full max-w-md">
          <span
            class="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant text-sm"
            >search</span
          >
          <input
            type="text"
            bind:value={lotSearchInput}
            placeholder="ロットコードで検索"
            class="w-full rounded-xl border border-outline-variant/15 bg-surface-container-low py-3 pl-12 pr-4 text-sm text-on-surface placeholder:text-outline-variant focus:ring-2 focus:ring-primary/30"
          />
        </div>
        <PaginationBar bind:page={lotPage} total={lotSummariesTotal} pageSize={LOT_PAGE_SIZE} disabled={lotListLoading} />
      </div>

      {#if lotListLoading && lotSummariesPage.length === 0}
        <div class="flex justify-center py-12">
          <span class="material-symbols-outlined text-3xl animate-spin text-primary">progress_activity</span>
        </div>
      {:else}
      <div class="space-y-3">
        {#each lotSummariesPage as lotSummary (lotSummary.lot_id)}
          <div class="flex flex-col gap-4 rounded-2xl border border-outline-variant/15 bg-surface px-5 py-4 md:flex-row md:items-center md:justify-between">
            <div>
              <div class="flex flex-wrap items-center gap-3">
                <p class="font-body text-lg font-semibold text-on-surface">{lotSummary.lot_code}</p>
              </div>
              <p class="mt-1 text-sm text-on-surface-variant">登録日 {formatDate(lotSummary.created_at)} / 単価 ¥{formatSpecNumber(lotSummary.unit_price, 1)}kg</p>
            </div>

            <div class="grid grid-cols-1 gap-4 text-left sm:grid-cols-3 sm:text-right md:min-w-0 md:w-full lg:min-w-[24rem]">
              <div class="min-w-0">
                <p class="text-[10px] uppercase tracking-widest text-on-surface-variant">残本数</p>
                <p class="mt-1 font-headline text-2xl leading-none tabular-nums text-on-surface whitespace-nowrap">{formatNumber(lotSummary.current_quantity)}</p>
              </div>
              <div class="min-w-0">
                <p class="text-[10px] uppercase tracking-widest text-on-surface-variant">残重量</p>
                <p class="mt-1 font-headline text-2xl leading-none tabular-nums text-on-surface whitespace-nowrap">{formatSpecNumber(lotSummary.current_weight, 3)}</p>
              </div>
              <div class="min-w-0">
                <p class="text-[10px] uppercase tracking-widest text-on-surface-variant">在庫金額</p>
                <p class="mt-1 font-headline text-2xl leading-none tabular-nums text-on-surface whitespace-nowrap">¥{formatNumber(Math.round(lotSummary.current_value))}</p>
              </div>
            </div>
          </div>
        {:else}
          <p class="py-10 text-center text-sm text-on-surface-variant">該当するロットがありません</p>
        {/each}
      </div>
      {/if}
    </section>

    <!-- Recent Transactions -->
    <section class="mt-20">
      <div class="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h3 class="font-headline text-2xl text-on-surface">最近の取引</h3>
          <a href="/history" class="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline">
            取引履歴を開く
            <span class="material-symbols-outlined text-base">open_in_new</span>
          </a>
        </div>
        <div class="relative w-full max-w-md md:max-w-sm">
          <span
            class="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant text-sm"
            >search</span
          >
          <input
            type="text"
            bind:value={recentSearchInput}
            placeholder="メモ・ロット・IDで検索"
            class="w-full rounded-xl border border-outline-variant/15 bg-surface-container-low py-3 pl-12 pr-4 text-sm text-on-surface placeholder:text-outline-variant focus:ring-2 focus:ring-primary/30"
          />
        </div>
      </div>

      <PaginationBar
        bind:page={recentPage}
        total={recentTotal}
        pageSize={RECENT_PAGE_SIZE}
        disabled={recentLoading}
        label="件の取引"
      />

      <div class="mt-6 space-y-3">
        {#if recentLoading && recentItems.length === 0}
          <div class="flex justify-center py-16">
            <span class="material-symbols-outlined text-3xl animate-spin text-primary">progress_activity</span>
          </div>
        {:else if recentItems.length === 0}
          <p class="py-12 text-center text-sm text-on-surface-variant">該当する取引がありません</p>
        {:else}
        {#each recentItems as tx}
          <div class="group flex items-center justify-between p-4 rounded-xl hover:bg-surface-container-lowest transition-all duration-300">
            <div class="flex items-center gap-6">
              <div class="w-12 h-12 rounded-lg bg-surface-container flex items-center justify-center">
                <span class="material-symbols-outlined {getTypeColor(tx.type)}">{getTypeIcon(tx.type)}</span>
              </div>
              <div>
                <p class="font-body font-bold text-on-surface">
                  {tx.type === 'in' ? '入庫' : tx.type === 'out' ? '出庫' : tx.type === 'return' ? '戻し' : '修正'}
                </p>
                <p class="text-xs text-on-surface-variant">{tx.lot_code || 'ロット不明'} / {tx.memo || 'メモなし'}</p>
              </div>
            </div>
            <div class="text-right">
              <p class="font-body {getTypeColor(tx.type)} font-bold">
                {tx.type === 'in' || tx.type === 'return' ? '+' : '-'} {tx.quantity} 本
              </p>
              <p class="text-[10px] text-on-surface-variant uppercase tracking-tighter">
                {formatDate(tx.created_at)}
              </p>
            </div>
          </div>
        {/each}
        {/if}
      </div>
    </section>
  </div>
{/if}
