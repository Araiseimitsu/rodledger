<script>
  import { onMount } from 'svelte';
  import { fetchDashboard, fetchLots, updateLot, updateMaterial } from '$lib/api';

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

  onMount(async () => {
    await loadDashboard();
  });

  async function loadDashboard(showLoader = true) {
    if (showLoader) loading = true;
    loadError = null;

    try {
      const nextDashboard = await fetchDashboard();
      const lots = await fetchLots(nextDashboard.material.id);

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

  function isOldestAvailableLot(lotSummary) {
    return dashboard?.oldest_available_lot_id === lotSummary?.lot_id;
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
      <p class="font-body text-on-surface-variant text-lg max-w-2xl leading-relaxed">
        {dashboard.material.name} 在庫管理ダッシュボード
      </p>
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
                <p class="text-sm text-on-surface-variant">保存後、単重は自動で再計算されます。</p>
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
      <div class="md:col-span-4 bg-surface-container-lowest border border-outline-variant/15 rounded-xl p-8 hover:bg-surface-container-low transition-colors duration-500">
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
      <div class="md:col-span-4 bg-surface-container-lowest border border-outline-variant/15 rounded-xl p-8 hover:bg-surface-container-low transition-colors duration-500">
        <div class="w-10 h-10 rounded-full bg-secondary-container flex items-center justify-center mb-6">
          <span class="material-symbols-outlined text-on-secondary-container">reorder</span>
        </div>
        <p class="text-on-surface-variant text-sm font-label mb-1">現在本数</p>
        <div class="flex items-baseline gap-2">
          <span class="text-5xl font-headline text-on-surface">{formatNumber(dashboard.total_effective_quantity ?? dashboard.total_quantity)}</span>
          <span class="text-xl font-label text-on-surface-variant">本</span>
        </div>
      </div>

      <!-- FIFO Lot Guide -->
      <div class="md:col-span-4 bg-white/60 backdrop-blur-xl border border-outline-variant/15 rounded-xl overflow-hidden">
        <div class="bg-primary/5 px-6 py-6">
          <div class="flex min-h-[12rem] flex-col rounded-2xl border border-primary/15 bg-surface/60 p-5">
            <div>
              <h4 class="font-label font-bold text-xs uppercase tracking-widest text-primary">FIFO 優先ロット</h4>
              <p class="mt-2 text-sm text-on-surface-variant">出庫は在庫が残っている最古ロットから順に処理します。</p>
            </div>
            <p class="mt-5 break-all font-headline text-xl leading-tight text-on-surface md:text-2xl">
              {#if dashboard.lot_summaries.length > 0 && dashboard.oldest_available_lot_id}
                {dashboard.lot_summaries.find((lot) => lot.lot_id === dashboard.oldest_available_lot_id)?.lot_code}
              {:else}
                在庫なし
              {/if}
            </p>
          </div>
        </div>
        <div class="p-6">
          <h4 class="font-label font-bold text-xs uppercase tracking-widest mb-2">ロット切替対応</h4>
          <p class="text-sm text-on-surface-variant">古いロットの戻しがあっても、残在庫があれば再び優先対象として扱います。</p>
        </div>
      </div>
    </div>

    <section class="mt-12 rounded-3xl border border-outline-variant/15 bg-surface-container-lowest p-8 md:p-10">
      <div class="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h3 class="font-headline text-2xl text-on-surface">ロット別在庫</h3>
          <p class="mt-2 text-sm text-on-surface-variant">総数を維持したまま、各ロットの残本数と残重量を確認できます。</p>
        </div>
        <p class="text-sm text-on-surface-variant">
          合計 {formatNumber(dashboard.total_effective_quantity ?? dashboard.total_quantity)} 本 / {formatSpecNumber(dashboard.total_weight, 3)} kg
        </p>
      </div>

      <div class="space-y-3">
        {#each dashboard.lot_summaries as lotSummary}
          <div class="flex flex-col gap-4 rounded-2xl border px-5 py-4 md:flex-row md:items-center md:justify-between {isOldestAvailableLot(lotSummary)
            ? 'border-primary/35 bg-primary/5'
            : 'border-outline-variant/15 bg-surface'}">
            <div>
              <div class="flex flex-wrap items-center gap-3">
                <p class="font-body text-lg font-semibold text-on-surface">{lotSummary.lot_code}</p>
                {#if isOldestAvailableLot(lotSummary)}
                  <span class="rounded-full bg-primary px-3 py-1 text-[10px] font-bold uppercase tracking-[0.2em] text-on-primary">FIFO 優先</span>
                {/if}
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
        {/each}
      </div>
    </section>

    <!-- Recent Transactions -->
    <section class="mt-20">
      <div class="flex justify-between items-center mb-10">
        <h3 class="font-headline text-2xl text-on-surface">最近の取引</h3>
      </div>
      <div class="space-y-3">
        {#each dashboard.recent_transactions as tx}
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
      </div>
    </section>
  </div>
{/if}
