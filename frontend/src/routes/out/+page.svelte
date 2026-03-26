<script>
  import { onMount } from 'svelte';
  import { fetchDashboard, fetchLots, createTransaction } from '$lib/api';
  import { goto } from '$app/navigation';

  let dashboard = $state(null);
  let lots = $state([]);
  let loading = $state(true);
  let error = $state('');
  let submitting = $state(false);

  // モード: out / return
  let mode = $state('out');

  // フォーム状態
  let entryMode = $state('quantity');
  let quantityStep = $state(10);
  let selectedLotId = $state('');
  let quantity = $state(0);
  let weight = $state(0);
  let memo = $state('');
  let idempotencyKey = $state('');

  const lotSummaries = $derived(dashboard?.lot_summaries ?? []);
  const availableLotSummaries = $derived(
    lotSummaries.filter((lot) => lot.current_quantity > 0 || lot.current_weight > 0)
  );
  const selectableLots = $derived(
    mode === 'out'
      ? lots.filter((lot) => availableLotSummaries.some((summary) => summary.lot_id === lot.id))
      : lots
  );
  const selectedLotSummary = $derived(
    lotSummaries.find((lot) => lot.lot_id === Number(selectedLotId)) ?? null
  );

  function normalizeQuantity(value) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return 0;
    return Math.max(0, Math.trunc(parsed));
  }

  function normalizeWeight(value) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return 0;
    return Number(Math.max(0, parsed).toFixed(3));
  }

  function syncWeightFromQuantity(nextQuantity) {
    if (!dashboard?.material) return;
    weight = normalizeWeight(nextQuantity * dashboard.material.weight_per_unit);
  }

  function calculateQuantityFromWeight(nextWeight) {
    if (!dashboard?.material?.weight_per_unit) return 0;
    return normalizeQuantity(Math.round(normalizeWeight(nextWeight) / dashboard.material.weight_per_unit));
  }

  function setEntryMode(nextMode) {
    if (entryMode === nextMode) return;
    entryMode = nextMode;

    if (nextMode === 'quantity') {
      quantity = normalizeQuantity(quantity);
      syncWeightFromQuantity(quantity);
      return;
    }

    quantity = 0;
  }

  function syncSelectedLotId() {
    if (mode === 'out') {
      const preferredLotId = dashboard?.oldest_available_lot_id;
      const preferredLot = selectableLots.find((lot) => lot.id === preferredLotId) ?? selectableLots[0];
      selectedLotId = preferredLot ? String(preferredLot.id) : '';
      return;
    }

    selectedLotId = lots.length > 0 ? String(lots[0].id) : '';
  }

  async function loadData() {
    loading = true;
    error = '';

    try {
      dashboard = await fetchDashboard();
      lots = await fetchLots(dashboard.material.id);
      syncSelectedLotId();
    } catch (e) {
      error = e?.message || 'データの取得に失敗しました';
      console.error(e);
    } finally {
      loading = false;
    }
  }

  onMount(async () => {
    await loadData();
  });

  // 数量変更時に重量を自動計算
  $effect(() => {
    if (entryMode === 'quantity' && dashboard?.material) {
      syncWeightFromQuantity(normalizeQuantity(quantity));
    }
  });

  // 数量増減
  function adjustQuantity(delta) {
    if (entryMode !== 'quantity') return;
    quantity = Math.max(0, normalizeQuantity(quantity) + delta);
  }

  function setQuantityStep(step) {
    quantityStep = step;
  }

  function handleQuantityInput(event) {
    quantity = normalizeQuantity(event.currentTarget.value);
  }

  function handleWeightInput(event) {
    weight = normalizeWeight(event.currentTarget.value);
  }

  function getLotOptionLabel(lot) {
    const summary = lotSummaries.find((item) => item.lot_id === lot.id);
    if (mode !== 'out' || !summary) {
      return `${lot.lot_code} (¥${lot.unit_price}/kg)`;
    }

    return `${lot.lot_code} (${summary.current_quantity}本 / ${summary.current_weight.toFixed(3)}kg)`;
  }

  function getSubmissionValues() {
    if (entryMode === 'quantity') {
      const normalizedQuantity = normalizeQuantity(quantity);
      return {
        quantity: normalizedQuantity,
        weight: normalizeWeight(normalizedQuantity * (dashboard?.material?.weight_per_unit ?? 0)),
      };
    }

    return {
      quantity: calculateQuantityFromWeight(weight),
      weight: normalizeWeight(weight),
    };
  }

  function canSubmit() {
    const submission = getSubmissionValues();
    return selectableLots.length > 0 && (submission.quantity > 0 || submission.weight > 0);
  }

  $effect(() => {
    mode;
    selectableLots;
    lots;

    if (!selectedLotId || !selectableLots.some((lot) => String(lot.id) === String(selectedLotId))) {
      syncSelectedLotId();
    }
  });

  function handleRetry() {
    loadData();
  }

  // フォーム送信
  async function handleSubmit(e) {
    e.preventDefault();
    const submission = getSubmissionValues();
    if (submitting || !selectedLotId || (submission.quantity <= 0 && submission.weight <= 0)) return;

    submitting = true;
    if (!idempotencyKey) {
      idempotencyKey = crypto.randomUUID();
    }
    try {
      const selectedLot = lots.find((l) => l.id === Number(selectedLotId));
      await createTransaction({
        material_id: dashboard.material.id,
        lot_id: Number(selectedLotId),
        type: mode,
        quantity: submission.quantity,
        weight: submission.weight,
        unit_price: selectedLot?.unit_price,
        memo: memo || undefined,
        idempotency_key: idempotencyKey,
      });
      idempotencyKey = '';
      goto('/history');
    } catch (e) {
      console.error(e);
      alert(e?.message || '登録に失敗しました');
    } finally {
      submitting = false;
    }
  }

  function formatDate(date) {
    return new Date().toLocaleDateString('ja-JP', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  }
</script>

{#if loading}
  <div class="flex items-center justify-center min-h-[60vh]">
    <span class="material-symbols-outlined text-4xl animate-spin">progress_activity</span>
  </div>
{:else if error}
  <main class="max-w-5xl mx-auto px-8 pt-32 pb-24">
    <div class="rounded-xl border border-error/20 bg-error/10 p-6 text-on-surface">
      <p class="font-semibold text-error mb-2">出庫画面の読み込みに失敗しました</p>
      <p class="text-sm text-on-surface-variant">{error}</p>
      <button
        type="button"
        onclick={handleRetry}
        class="mt-4 px-4 py-2 rounded-lg bg-surface-container-high text-on-surface text-sm font-semibold"
      >
        再試行
      </button>
    </div>
  </main>
{:else if dashboard}
  <main class="pt-32 pb-24 px-8 md:px-16 lg:px-32 max-w-5xl mx-auto w-full">
    <!-- Header -->
    <section class="mb-12">
      <h2 class="font-headline text-4xl lg:text-5xl font-bold tracking-tight text-on-surface mb-2">
        {mode === 'out' ? '出庫登録' : '戻し登録'}
      </h2>
      <p class="font-body text-on-surface-variant text-lg">
        {mode === 'out' ? '材料の出庫を記録します。' : '余剰材料の戻しを記録します。'}
      </p>
    </section>

    <!-- Entry Card -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <div class="lg:col-span-8 bg-surface-container-lowest rounded-xl p-8 shadow-sm">
        <!-- Mode Toggle -->
        <div class="flex justify-center mb-10">
          <div class="inline-flex p-1 bg-surface-container rounded-full w-full max-w-xs">
            <button
              type="button"
              onclick={() => (mode = 'out')}
              class="flex-1 py-2 px-6 rounded-full text-sm font-semibold transition-all {mode === 'out'
                ? 'bg-error text-on-error shadow-sm'
                : 'text-on-surface-variant hover:text-on-surface'}"
            >
              出庫
            </button>
            <button
              type="button"
              onclick={() => (mode = 'return')}
              class="flex-1 py-2 px-6 rounded-full text-sm font-semibold transition-all {mode === 'return'
                ? 'bg-secondary text-on-secondary shadow-sm'
                : 'text-on-surface-variant hover:text-on-surface'}"
            >
              戻し
            </button>
          </div>
        </div>

        <form onsubmit={handleSubmit} class="space-y-10">
          <!-- Lot Selection -->
          <div class="space-y-3">
            {#if mode === 'out' && dashboard?.oldest_available_lot_id}
              <div class="rounded-2xl border border-primary/20 bg-primary/5 px-4 py-3 text-sm text-on-surface">
                FIFO に従い、現在は
                <span class="font-semibold">{lotSummaries.find((lot) => lot.lot_id === dashboard.oldest_available_lot_id)?.lot_code}</span>
                から出庫します。
              </div>
            {/if}
            <label for="lot-select" class="block font-label text-sm font-semibold tracking-wider text-on-surface-variant uppercase"
              >ロット選択</label
            >
            <div class="relative">
              <select
                id="lot-select"
                bind:value={selectedLotId}
                disabled={selectableLots.length === 0}
                class="w-full bg-surface-container-low border-none rounded-xl py-4 px-6 text-on-surface focus:ring-2 focus:ring-primary/40 transition-all appearance-none cursor-pointer text-lg font-medium"
              >
                {#if selectableLots.length === 0}
                  <option value="">選択可能なロットがありません</option>
                {:else}
                  {#each selectableLots as lot}
                    <option value={lot.id}>{getLotOptionLabel(lot)}</option>
                  {/each}
                {/if}
              </select>
              <span
                class="material-symbols-outlined absolute right-4 top-1/2 -translate-y-1/2 text-outline-variant pointer-events-none"
                >expand_more</span
              >
            </div>
          </div>

          <!-- Quantity / Weight -->
          <div class="space-y-6 border-y border-outline-variant/15 py-8">
            <div class="flex flex-col gap-3 rounded-2xl bg-surface-container-low p-3 md:flex-row md:items-center md:justify-between">
              <div>
                <p class="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">入力方法</p>
                <p class="mt-1 text-sm text-on-surface-variant">
                  {mode === 'out' ? '本数ベースと重量ベースのどちらでも出庫できます。' : '本数ベースと重量ベースのどちらでも戻し登録できます。'}
                </p>
              </div>
              <div class="inline-flex rounded-full bg-surface-container p-1">
                <button
                  type="button"
                  onclick={() => setEntryMode('quantity')}
                  class="rounded-full px-5 py-2 text-sm font-semibold transition-colors {entryMode === 'quantity'
                    ? mode === 'out'
                      ? 'bg-error text-on-error'
                      : 'bg-secondary text-on-secondary'
                    : 'text-on-surface-variant hover:text-on-surface'}"
                >
                  本数入力
                </button>
                <button
                  type="button"
                  onclick={() => setEntryMode('weight')}
                  class="rounded-full px-5 py-2 text-sm font-semibold transition-colors {entryMode === 'weight'
                    ? mode === 'out'
                      ? 'bg-error text-on-error'
                      : 'bg-secondary text-on-secondary'
                    : 'text-on-surface-variant hover:text-on-surface'}"
                >
                  重量入力
                </button>
              </div>
            </div>

            <div class="grid grid-cols-1 2xl:grid-cols-2 gap-6 items-start">
              <div class="space-y-3 min-w-0">
                <div class="flex items-center justify-between gap-4">
                  <label for="quantity-input" class="block font-label text-sm font-semibold tracking-wider text-on-surface-variant uppercase"
                    >{mode === 'out' ? '数量（本）' : '戻し数量（本）'}</label
                  >
                  {#if entryMode === 'quantity'}
                    <div class="inline-flex rounded-full bg-surface-container p-1">
                      <button
                        type="button"
                        onclick={() => setQuantityStep(1)}
                        class="rounded-full px-3 py-1 text-xs font-semibold transition-colors {quantityStep === 1
                          ? mode === 'out'
                            ? 'bg-error text-on-error'
                            : 'bg-secondary text-on-secondary'
                          : 'text-on-surface-variant hover:text-on-surface'}"
                      >
                        1本
                      </button>
                      <button
                        type="button"
                        onclick={() => setQuantityStep(10)}
                        class="rounded-full px-3 py-1 text-xs font-semibold transition-colors {quantityStep === 10
                          ? mode === 'out'
                            ? 'bg-error text-on-error'
                            : 'bg-secondary text-on-secondary'
                          : 'text-on-surface-variant hover:text-on-surface'}"
                      >
                        10本
                      </button>
                    </div>
                  {:else}
                    <span class="text-xs text-outline-variant">重量から換算した本数を登録します</span>
                  {/if}
                </div>
                {#if entryMode === 'quantity'}
                  <div class="flex items-center gap-3 min-w-0">
                    <button
                      type="button"
                      onclick={() => adjustQuantity(-quantityStep)}
                      class="w-14 h-14 shrink-0 rounded-full bg-surface-container hover:bg-surface-container-high transition-colors"
                    >
                      <span class="material-symbols-outlined">remove</span>
                    </button>
                    <input
                      id="quantity-input"
                      type="number"
                      value={quantity}
                      min="0"
                      step={quantityStep}
                      oninput={handleQuantityInput}
                      class="no-spinner min-w-0 w-full text-center tabular-nums leading-none text-2xl md:text-3xl lg:text-4xl font-bold bg-surface-container-low border-none rounded-xl py-4 px-4 md:px-6 text-on-surface focus:ring-2 focus:ring-primary/40"
                    />
                    <button
                      type="button"
                      onclick={() => adjustQuantity(quantityStep)}
                      class="w-14 h-14 shrink-0 rounded-full bg-surface-container hover:bg-surface-container-high transition-colors"
                    >
                      <span class="material-symbols-outlined">add</span>
                    </button>
                  </div>
                {:else}
                  <div class="flex items-center justify-center rounded-xl bg-surface-container-low py-6 px-6 text-2xl md:text-3xl font-bold text-on-surface-variant">
                    {calculateQuantityFromWeight(weight).toLocaleString('ja-JP')}
                  </div>
                {/if}
              </div>

              <div class="space-y-3 min-w-0">
                <div class="flex items-center justify-between gap-4">
                  <label for="weight-input" class="block font-label text-sm font-semibold tracking-wider text-on-surface-variant uppercase"
                    >重量（kg）</label
                  >
                  <span class="text-xs text-outline-variant">{entryMode === 'quantity' ? '本数から自動計算' : '直接入力'}</span>
                </div>
                <div class="space-y-2 w-full min-w-0">
                  <input
                    id="weight-input"
                    type="number"
                    value={weight}
                    step="0.001"
                    min="0"
                    readonly={entryMode === 'quantity'}
                    oninput={handleWeightInput}
                    class="no-spinner w-full bg-surface-container-low border-none rounded-xl py-4 px-6 text-2xl md:text-3xl lg:text-4xl font-bold tabular-nums text-on-surface {entryMode === 'quantity'
                      ? 'opacity-70'
                      : 'focus:ring-2 focus:ring-primary/40'}"
                  />
                  <span class="block text-right whitespace-nowrap text-outline-variant text-sm">
                    {entryMode === 'quantity' ? '自動計算' : mode === 'out' ? '重量のみの出庫にも対応' : '重量のみの戻しにも対応'}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- Memo -->
          <div class="space-y-3">
            <label for="memo-input" class="block font-label text-sm font-semibold tracking-wider text-on-surface-variant uppercase"
              >メモ</label
            >
            <input
              id="memo-input"
              type="text"
              bind:value={memo}
              placeholder="必要に応じて入力"
              class="w-full bg-surface-container-low border-none rounded-xl py-4 px-6 text-on-surface focus:ring-2 focus:ring-primary/40"
            />
          </div>

          <!-- Submit -->
          <div class="flex flex-col md:flex-row items-center justify-between gap-6 pt-4">
            <div class="flex items-center gap-2 text-on-surface-variant">
              <span class="material-symbols-outlined text-sm">schedule</span>
              <span class="text-xs font-medium">{formatDate(new Date())}</span>
            </div>
            <div class="flex gap-4 w-full md:w-auto">
              <button
                type="button"
                onclick={() => goto('/')}
                class="flex-1 md:flex-none px-8 py-4 rounded-lg bg-surface-container-highest text-on-secondary-container font-semibold text-sm hover:opacity-80 transition-all"
              >
                キャンセル
              </button>
              <button
                type="submit"
                disabled={submitting || !canSubmit()}
                class="flex-1 md:flex-none px-12 py-4 rounded-lg font-semibold text-sm shadow-sm hover:opacity-90 active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 {mode ===
                'out'
                  ? 'bg-error text-on-error'
                  : 'bg-secondary text-on-secondary'}"
              >
                {#if submitting}
                  <span class="material-symbols-outlined animate-spin">progress_activity</span>
                {:else}
                  <span class="material-symbols-outlined">{mode === 'out' ? 'north_east' : 'assignment_return'}</span>
                {/if}
                {mode === 'out' ? '出庫確定' : '戻し確定'}
              </button>
            </div>
          </div>
        </form>
      </div>

      <!-- Sidebar -->
      <div class="lg:col-span-4 flex flex-col gap-6">
        <!-- Current Stock -->
        <div class="bg-surface-container-high rounded-xl p-6">
          <div class="flex items-center gap-4 mb-4">
            <div class="w-12 h-12 rounded bg-surface-container-highest flex items-center justify-center">
              <span class="material-symbols-outlined text-primary">inventory_2</span>
            </div>
            <div>
              <p class="text-[10px] uppercase tracking-wider font-bold text-on-surface-variant">現在在庫</p>
              <p class="font-headline text-2xl text-on-surface"
                >{dashboard.total_quantity.toLocaleString()}
                <span class="text-sm font-sans font-normal text-on-surface-variant">本</span></p
              >
            </div>
          </div>
          <div class="pt-4 border-t border-outline-variant/15">
            <p class="text-xs text-on-surface-variant">重量: {dashboard.total_weight.toFixed(1)} kg</p>
          </div>
        </div>

        <div class="bg-surface-container-lowest rounded-xl border border-outline-variant/15 p-6">
          <h3 class="font-label text-xs font-bold tracking-widest text-on-surface-variant uppercase">選択ロット在庫</h3>
          {#if selectedLotSummary}
            <div class="mt-4 space-y-3">
              <div>
                <p class="font-semibold text-on-surface">{selectedLotSummary.lot_code}</p>
                <p class="text-xs text-on-surface-variant">残重量 {selectedLotSummary.current_weight.toFixed(3)} kg</p>
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div class="rounded-xl bg-surface-container p-4">
                  <p class="text-[10px] uppercase tracking-widest text-on-surface-variant">残本数</p>
                  <p class="mt-2 font-headline text-3xl text-on-surface">{selectedLotSummary.current_quantity}</p>
                </div>
                <div class="rounded-xl bg-surface-container p-4">
                  <p class="text-[10px] uppercase tracking-widest text-on-surface-variant">単価</p>
                  <p class="mt-2 font-headline text-3xl text-on-surface">¥{selectedLotSummary.unit_price}</p>
                </div>
              </div>
            </div>
          {:else}
            <p class="mt-4 text-sm text-on-surface-variant">{mode === 'out' ? '出庫可能なロット在庫がありません。' : '戻し先ロットを選択してください。'}</p>
          {/if}
        </div>

        <div class="bg-surface-container-low rounded-xl p-6 space-y-4">
          <h3 class="font-label text-xs font-bold tracking-widest text-on-surface-variant uppercase">FIFO ロット順</h3>
          <div class="space-y-3">
            {#each lotSummaries as lot}
              <div class="rounded-xl border px-4 py-3 {dashboard.oldest_available_lot_id === lot.lot_id
                ? 'border-primary/30 bg-primary/5'
                : 'border-outline-variant/15 bg-surface-container'}">
                <div class="flex items-center justify-between gap-4">
                  <div>
                    <p class="font-medium text-on-surface">{lot.lot_code}</p>
                    <p class="text-xs text-on-surface-variant">{lot.current_weight.toFixed(3)} kg</p>
                  </div>
                  <div class="text-right">
                    <p class="font-semibold text-on-surface">{lot.current_quantity} 本</p>
                    {#if dashboard.oldest_available_lot_id === lot.lot_id}
                      <p class="text-[10px] uppercase tracking-widest text-primary">現在優先</p>
                    {/if}
                  </div>
                </div>
              </div>
            {/each}
          </div>
        </div>

        <!-- Material Info -->
        <div class="bg-surface-container-low rounded-xl p-6 space-y-4">
          <h3 class="font-label text-xs font-bold tracking-widest text-on-surface-variant uppercase">材料仕様</h3>
          <div class="space-y-3">
            <div class="flex justify-between items-center">
              <span class="text-on-surface-variant text-sm">材料名</span>
              <span class="font-medium text-on-surface">{dashboard.material.name}</span>
            </div>
            <div class="flex justify-between items-center">
              <span class="text-on-surface-variant text-sm">直径</span>
              <span class="font-medium text-on-surface">{dashboard.material.diameter} mm</span>
            </div>
            <div class="flex justify-between items-center">
              <span class="text-on-surface-variant text-sm">長さ</span>
              <span class="font-medium text-on-surface">{dashboard.material.length} mm</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </main>
{/if}
