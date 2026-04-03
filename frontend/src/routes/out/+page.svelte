<script>
  import { onMount } from 'svelte';
  import {
    fetchDashboard,
    fetchLots,
    createTransaction,
    createIdempotencyKey,
    fetchStockLocations,
    fetchLotLocationStocks,
  } from '$lib/api';
  import { filterRowsWithStock } from '$lib/lotLocationStock.js';
  import {
    readLastStockLocationId,
    sameStringArray,
    writeLastStockLocationId,
  } from '$lib/lastStockLocationPreference.js';
  import { firstLotIdString, sortLotsOldestFirst } from '$lib/lotSort.js';
  import { parseIntegerQuantityInput, preventQuantityNonIntegerKeys } from '$lib/quantityInput.js';
  import {
    beforeWeightInput,
    parseWeightInputToNumber,
    preventWeightHalfWidthKeys,
    sanitizeWeightInputText,
    weightNumberToInputString,
  } from '$lib/weightInput.js';
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
  /** 重量入力モード時のみ。数値に正規化すると「456.」が「456」になりカーソルが先頭へ飛ぶため文字列で保持 */
  let weightInputText = $state('');
  let memo = $state('');
  let idempotencyKey = $state('');
  let stockLocations = $state([]);
  let selectedLocationIds = $state([]);
  let lotLocationStocks = $state([]);
  let lotLocationFetchId = 0;

  const lotSummaries = $derived(dashboard?.lot_summaries ?? []);
  const availableLotSummaries = $derived(lotSummaries.filter((lot) => lot.current_quantity > 0));
  const selectableLots = $derived(
    mode === 'out'
      ? sortLotsOldestFirst(
          lots.filter((lot) => availableLotSummaries.some((summary) => summary.lot_id === lot.id)),
        )
      : lots
  );
  const selectedLotSummary = $derived(
    lotSummaries.find((lot) => lot.lot_id === Number(selectedLotId)) ?? null
  );

  const locationsWithStock = $derived(filterRowsWithStock(lotLocationStocks));

  const weightReadonlyDisplay = $derived.by(() => {
    const w = normalizeWeight(weight);
    if (w === 0) return '0';
    return String(parseFloat(w.toFixed(3)));
  });

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
    weightInputText = weightNumberToInputString(weight);
  }

  function syncSelectedLotId() {
    selectedLotId = firstLotIdString(selectableLots);
  }

  /** 有効な id のみ残し、空なら直近の選択または先頭1件を入れる */
  function assignSelectedLocationIds(availableIds, firstId) {
    const filtered = selectedLocationIds.filter((id) => availableIds.has(String(id)));
    if (filtered.length > 0) {
      if (!sameStringArray(filtered, selectedLocationIds)) {
        selectedLocationIds = filtered;
      }
      return;
    }
    const preferred = readLastStockLocationId();
    if (preferred != null && availableIds.has(String(preferred))) {
      const next = [String(preferred)];
      if (!sameStringArray(next, selectedLocationIds)) {
        selectedLocationIds = next;
      }
      return;
    }
    const next = [firstId];
    if (!sameStringArray(next, selectedLocationIds)) {
      selectedLocationIds = next;
    }
  }

  function syncSelectedLocations() {
    if (mode === 'return') {
      if (stockLocations.length === 0) {
        if (selectedLocationIds.length > 0) {
          selectedLocationIds = [];
        }
        return;
      }
      const availableIds = new Set(stockLocations.map((loc) => String(loc.id)));
      assignSelectedLocationIds(availableIds, String(stockLocations[0].id));
      return;
    }
    const rows = locationsWithStock;
    if (rows.length === 0) {
      if (selectedLocationIds.length > 0) {
        selectedLocationIds = [];
      }
      return;
    }
    const availableIds = new Set(rows.map((r) => String(r.location_id)));
    assignSelectedLocationIds(availableIds, String(rows[0].location_id));
  }

  function getSelectedLocationLabels() {
    const selected = new Set(selectedLocationIds.map(String));
    if (mode === 'return') {
      return stockLocations
        .filter((loc) => selected.has(String(loc.id)))
        .map((loc) => String(loc.name).trim());
    }
    return locationsWithStock
      .filter((row) => selected.has(String(row.location_id)))
      .map((row) => String(row.location_name).trim());
  }

  function buildLocationNote() {
    return getSelectedLocationLabels().join(', ');
  }

  function isLocationSelected(locationId) {
    return selectedLocationIds.includes(String(locationId));
  }

  async function refreshLotLocations() {
    if (!selectedLotId) {
      lotLocationStocks = [];
      syncSelectedLocations();
      return;
    }
    if (mode === 'return') {
      syncSelectedLocations();
      return;
    }
    const fetchId = ++lotLocationFetchId;
    lotLocationStocks = [];
    try {
      const res = await fetchLotLocationStocks(Number(selectedLotId));
      if (fetchId !== lotLocationFetchId) return;
      lotLocationStocks = res.items ?? [];
    } catch (e) {
      if (fetchId !== lotLocationFetchId) return;
      console.error(e);
      lotLocationStocks = [];
    }
    syncSelectedLocations();
  }

  async function loadData() {
    loading = true;
    error = '';

    try {
      dashboard = await fetchDashboard();
      const { items } = await fetchLots(dashboard.material.id);
      lots = items;
      stockLocations = await fetchStockLocations();
      syncSelectedLotId();
      await refreshLotLocations();
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
    quantity = parseIntegerQuantityInput(event.currentTarget.value);
  }

  function handleWeightInput(event) {
    weightInputText = sanitizeWeightInputText(event.currentTarget.value);
    weight = parseWeightInputToNumber(weightInputText);
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
    if (mode === 'out') {
      if (selectedLocationIds.length === 0 || locationsWithStock.length === 0) return false;
    } else if (stockLocations.length > 0 && selectedLocationIds.length === 0) {
      return false;
    }
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

  $effect(() => {
    selectedLotId;
    mode;
    void refreshLotLocations();
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
    try {
      if (!idempotencyKey) {
        idempotencyKey = createIdempotencyKey();
      }

      const selectedLot = lots.find((l) => l.id === Number(selectedLotId));
      const primaryLocationId = selectedLocationIds[0] ? Number(selectedLocationIds[0]) : undefined;
      await createTransaction({
        material_id: dashboard.material.id,
        lot_id: Number(selectedLotId),
        type: mode,
        quantity: submission.quantity,
        weight: submission.weight,
        unit_price: selectedLot?.unit_price,
        memo: memo || undefined,
        location_note: buildLocationNote() || undefined,
        idempotency_key: idempotencyKey,
        location_id: primaryLocationId,
      });
      if (primaryLocationId != null) {
        writeLastStockLocationId(primaryLocationId);
      }
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
                    <option value={String(lot.id)}>{getLotOptionLabel(lot)}</option>
                  {/each}
                {/if}
              </select>
              <span
                class="material-symbols-outlined absolute right-4 top-1/2 -translate-y-1/2 text-outline-variant pointer-events-none"
                >expand_more</span
              >
            </div>
          </div>

          <!-- Stock location -->
          <div class="space-y-4">
            <p class="block font-label text-sm font-semibold tracking-wider text-on-surface-variant uppercase">
              {mode === 'out' ? '出庫元（保管場所・複数選択）' : '戻し先（保管場所・複数選択）'}
            </p>

            {#if mode === 'out'}
              {#if stockLocations.length === 0}
                <p class="text-sm text-on-surface-variant">保管場所を読み込み中、または取得に失敗しました。</p>
              {:else if locationsWithStock.length === 0}
                <p class="text-sm text-on-surface-variant">
                  このロットで在庫のある棚がありません（読み込み中、または別ロットを選んでください）。
                </p>
              {:else}
                <div class="rounded-2xl bg-surface-container-low p-4">
                  <div class="mb-4 flex flex-wrap gap-2">
                    {#each getSelectedLocationLabels() as label}
                      <span class="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">{label}</span>
                    {/each}
                  </div>
                  <div class="grid max-h-64 grid-cols-2 gap-2 overflow-y-auto md:grid-cols-4 xl:grid-cols-5">
                    {#each locationsWithStock as row}
                      <label
                        class="flex cursor-pointer items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold transition-colors {isLocationSelected(row.location_id)
                          ? 'bg-primary/10 text-on-surface'
                          : 'bg-surface-container text-on-surface hover:bg-surface-container-high'}"
                      >
                        <input
                          type="checkbox"
                          bind:group={selectedLocationIds}
                          value={String(row.location_id)}
                          class="h-4 w-4 rounded border-outline-variant text-primary focus:ring-primary"
                        />
                        <span class="flex min-w-0 flex-col">
                          <span>{String(row.location_name).trim()}</span>
                          <span class="text-xs font-normal text-on-surface-variant tabular-nums"
                            >{row.current_quantity}本 / {row.current_weight.toFixed(3)}kg</span
                          >
                        </span>
                      </label>
                    {/each}
                  </div>
                </div>
              {/if}
            {:else if stockLocations.length === 0}
              <p class="text-sm text-on-surface-variant">保管場所を読み込み中、または取得に失敗しました。</p>
            {:else}
              <div class="rounded-2xl bg-surface-container-low p-4">
                <div class="mb-4 flex flex-wrap gap-2">
                  {#each getSelectedLocationLabels() as label}
                    <span class="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">{label}</span>
                  {/each}
                </div>
                <div class="grid max-h-64 grid-cols-2 gap-2 overflow-y-auto md:grid-cols-4 xl:grid-cols-5">
                  {#each stockLocations as loc}
                    <label
                      class="flex cursor-pointer items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold transition-colors {isLocationSelected(loc.id)
                        ? 'bg-primary/10 text-on-surface'
                        : 'bg-surface-container text-on-surface hover:bg-surface-container-high'}"
                    >
                      <input
                        type="checkbox"
                        bind:group={selectedLocationIds}
                        value={String(loc.id)}
                        class="h-4 w-4 rounded border-outline-variant text-primary focus:ring-primary"
                      />
                      <span>{String(loc.name).trim()}</span>
                    </label>
                  {/each}
                </div>
              </div>
            {/if}
          </div>

          <!-- Quantity / Weight -->
          <div class="space-y-6 border-y border-outline-variant/15 py-8">
            <div class="flex flex-col gap-3 rounded-2xl bg-surface-container-low p-3 md:flex-row md:items-center md:justify-between">
              <p class="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">入力方法</p>
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

            <div class="grid grid-cols-1 gap-6 items-start">
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
                      step="1"
                      inputmode="numeric"
                      onkeydown={preventQuantityNonIntegerKeys}
                      oninput={handleQuantityInput}
                      class="no-spinner numeric-input-fluid numeric-input-visible min-w-0 w-full flex-1 text-center tabular-nums font-bold bg-surface-container-low border-none rounded-xl py-4 px-4 md:px-6 text-on-surface focus:ring-2 focus:ring-primary/40"
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
                  <div
                    class="flex min-w-0 w-full items-center justify-center overflow-x-auto rounded-xl bg-surface-container-low py-6 px-6 numeric-input-fluid font-bold tabular-nums text-on-surface-variant"
                  >
                    {calculateQuantityFromWeight(weight).toLocaleString('ja-JP')}
                  </div>
                {/if}
              </div>

              <div class="space-y-3 min-w-0">
                <label for="weight-input" class="block font-label text-sm font-semibold tracking-wider text-on-surface-variant uppercase"
                  >重量（kg）</label
                >
                <div class="space-y-2 w-full min-w-0">
                  <input
                    id="weight-input"
                    type="text"
                    inputmode="decimal"
                    autocomplete="off"
                    readonly={entryMode === 'quantity'}
                    value={entryMode === 'quantity' ? weightReadonlyDisplay : weightInputText}
                    onbeforeinput={entryMode === 'quantity' ? undefined : beforeWeightInput}
                    oninput={entryMode === 'quantity' ? undefined : handleWeightInput}
                    onkeydown={entryMode === 'quantity' ? undefined : preventWeightHalfWidthKeys}
                    class="no-spinner numeric-input-fluid numeric-input-visible w-full min-w-0 bg-surface-container-low border-none rounded-xl py-4 px-6 text-right font-bold tabular-nums text-on-surface {entryMode === 'quantity'
                      ? 'opacity-70'
                      : 'focus:ring-2 focus:ring-primary/40'}"
                  />
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
                >{(dashboard.total_effective_quantity ?? dashboard.total_quantity).toLocaleString()}
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
