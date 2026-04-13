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
  let stockLocations = $state([]);
  let loading = $state(true);
  let error = $state('');
  let submitting = $state(false);

  let entryMode = $state('quantity');
  let quantityStep = $state(10);
  let selectedLotId = $state('');
  let locationFromIds = $state([]);
  let locationToIds = $state([]);
  let quantity = $state(0);
  let weight = $state(0);
  let weightInputText = $state('');
  let memo = $state('');
  let idempotencyKey = $state('');
  let lotLocationStocks = $state([]);

  const lotSummaries = $derived(dashboard?.lot_summaries ?? []);
  const availableLotSummaries = $derived(lotSummaries.filter((lot) => lot.current_quantity > 0));
  const selectableLots = $derived(
    sortLotsOldestFirst(
      lots.filter((lot) => availableLotSummaries.some((summary) => summary.lot_id === lot.id)),
    ),
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

  function syncDefaultLot() {
    selectedLotId = firstLotIdString(selectableLots);
  }

  function setLocationFromIds(next) {
    if (!sameStringArray(next, locationFromIds)) {
      locationFromIds = next;
    }
  }

  function setLocationToIds(next) {
    if (!sameStringArray(next, locationToIds)) {
      locationToIds = next;
    }
  }

  function syncLocationPair() {
    if (locationsWithStock.length > 0) {
      const validFrom = new Set(locationsWithStock.map((r) => String(r.location_id)));
      const filteredFrom = locationFromIds.filter((id) => validFrom.has(String(id)));
      if (filteredFrom.length > 0) {
        setLocationFromIds(filteredFrom);
      } else {
        const preferred = readLastStockLocationId();
        const nextFrom =
          preferred != null && validFrom.has(String(preferred))
            ? [String(preferred)]
            : [String(locationsWithStock[0].location_id)];
        setLocationFromIds(nextFrom);
      }
    } else if (locationFromIds.length > 0) {
      locationFromIds = [];
    }

    const fromPrimary = Number(locationFromIds[0]);
    const toCandidates = stockLocations.filter((loc) => loc.id !== fromPrimary);
    if (toCandidates.length === 0) {
      setLocationToIds([]);
      return;
    }
    const validTo = new Set(toCandidates.map((loc) => String(loc.id)));
    const filteredTo = locationToIds.filter((id) => validTo.has(String(id)));
    if (filteredTo.length > 0) {
      setLocationToIds(filteredTo);
    } else {
      setLocationToIds([]);
    }
  }

  function getSelectedFromLabels() {
    const selected = new Set(locationFromIds.map(String));
    return locationsWithStock
      .filter((row) => selected.has(String(row.location_id)))
      .map((row) => String(row.location_name).trim());
  }

  function getSelectedToLabels() {
    const selected = new Set(locationToIds.map(String));
    return stockLocations
      .filter((loc) => selected.has(String(loc.id)))
      .map((loc) => String(loc.name).trim());
  }

  function isLocationFromSelected(locationId) {
    return locationFromIds.includes(String(locationId));
  }

  function isLocationToSelected(locationId) {
    return locationToIds.includes(String(locationId));
  }

  async function refreshLotLocations() {
    lotLocationStocks = [];
    if (!selectedLotId) return;
    try {
      const res = await fetchLotLocationStocks(Number(selectedLotId));
      lotLocationStocks = res.items ?? [];
    } catch (e) {
      console.error(e);
    }
    syncLocationPair();
  }

  async function loadData() {
    loading = true;
    error = '';
    try {
      dashboard = await fetchDashboard();
      const { items } = await fetchLots(dashboard.material.id);
      lots = items;
      stockLocations = await fetchStockLocations();
      syncDefaultLot();
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

  $effect(() => {
    if (entryMode === 'quantity' && dashboard?.material) {
      syncWeightFromQuantity(normalizeQuantity(quantity));
    }
  });

  $effect(() => {
    selectedLotId;
    refreshLotLocations();
  });

  $effect(() => {
    locationFromIds;
    locationsWithStock;
    stockLocations;
    syncLocationPair();
  });

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

  function getSubmissionValues() {
    if (entryMode === 'quantity') {
      const normalizedQuantity = normalizeQuantity(quantity);
      return {
        quantity: normalizedQuantity,
        weight: normalizeWeight(normalizedQuantity * (dashboard?.material?.weight_per_unit ?? 0)),
      };
    }
    const calcQuantity = calculateQuantityFromWeight(weight);
    return {
      quantity: calcQuantity,
      weight: normalizeWeight(calcQuantity * (dashboard?.material?.weight_per_unit ?? 0)),
    };
  }

  function canSubmit() {
    const submission = getSubmissionValues();
    if (selectableLots.length === 0) return false;
    if (!selectedLotId || locationFromIds.length === 0 || locationToIds.length === 0) return false;
    if (Number(locationFromIds[0]) === Number(locationToIds[0])) return false;
    return submission.quantity > 0 || submission.weight > 0;
  }

  $effect(() => {
    selectableLots;
    lots;
    if (!selectedLotId || !selectableLots.some((lot) => String(lot.id) === String(selectedLotId))) {
      syncDefaultLot();
    }
  });

  function handleRetry() {
    loadData();
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const submission = getSubmissionValues();
    if (submitting || !canSubmit()) return;

    submitting = true;
    try {
      if (!idempotencyKey) {
        idempotencyKey = createIdempotencyKey();
      }

      const selectedLot = lots.find((l) => l.id === Number(selectedLotId));
      const fromId = Number(locationFromIds[0]);
      const toId = Number(locationToIds[0]);
      await createTransaction({
        material_id: dashboard.material.id,
        lot_id: Number(selectedLotId),
        type: 'transfer',
        quantity: submission.quantity,
        weight: submission.weight,
        unit_price: selectedLot?.unit_price,
        memo: memo || undefined,
        idempotency_key: idempotencyKey,
        location_from_id: fromId,
        location_to_id: toId,
      });
      writeLastStockLocationId(fromId);
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
      <p class="font-semibold text-error mb-2">移動画面の読み込みに失敗しました</p>
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
    <section class="mb-12">
      <h2 class="font-headline text-4xl lg:text-5xl font-bold tracking-tight text-on-surface mb-2">場所移動</h2>
    </section>

    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <div class="lg:col-span-12 bg-surface-container-lowest rounded-xl p-8 shadow-sm">
        <form onsubmit={handleSubmit} class="space-y-10">
          <div class="space-y-3">
            <label for="lot-select" class="block font-label text-sm font-semibold tracking-wider text-on-surface-variant uppercase"
              >ロット</label
            >
            <div class="relative">
              <select
                id="lot-select"
                bind:value={selectedLotId}
                disabled={selectableLots.length === 0}
                class="w-full bg-surface-container-low border-none rounded-xl py-4 px-6 text-on-surface focus:ring-2 focus:ring-primary/40 transition-all appearance-none cursor-pointer text-lg font-medium"
              >
                {#if selectableLots.length === 0}
                  <option value="">移動可能なロットがありません</option>
                {:else}
                  {#each selectableLots as lot}
                    <option value={String(lot.id)}>{lot.lot_code}</option>
                  {/each}
                {/if}
              </select>
              <span
                class="material-symbols-outlined absolute right-4 top-1/2 -translate-y-1/2 text-outline-variant pointer-events-none"
                >expand_more</span
              >
            </div>
          </div>

          <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div class="space-y-4">
              <p class="block font-label text-sm font-semibold tracking-wider text-on-surface-variant uppercase">
                移動元（複数選択）
              </p>
              {#if locationsWithStock.length === 0}
                <p class="text-sm text-on-surface-variant">在庫のある場所がありません（別ロットを選んでください）。</p>
              {:else}
                <div class="rounded-2xl bg-surface-container-low p-4">
                  <div class="mb-4 flex flex-wrap gap-2">
                    {#each getSelectedFromLabels() as label}
                      <span class="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">{label}</span>
                    {/each}
                  </div>
                  <div class="grid max-h-64 grid-cols-2 gap-2 overflow-y-auto md:grid-cols-3">
                    {#each locationsWithStock as row}
                      <label
                        class="flex cursor-pointer items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold transition-colors {isLocationFromSelected(row.location_id)
                          ? 'bg-primary/10 text-on-surface'
                          : 'bg-surface-container text-on-surface hover:bg-surface-container-high'}"
                      >
                        <input
                          type="checkbox"
                          bind:group={locationFromIds}
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
            </div>

            <div class="space-y-4">
              <p class="block font-label text-sm font-semibold tracking-wider text-on-surface-variant uppercase">
                移動先（複数選択）
              </p>
              {#if stockLocations.length === 0}
                <p class="text-sm text-on-surface-variant">保管場所を読み込み中、または取得に失敗しました。</p>
              {:else if locationFromIds.length === 0}
                <p class="text-sm text-on-surface-variant">先に移動元を選んでください。</p>
              {:else}
                {@const fromPrimary = Number(locationFromIds[0])}
                {@const toCandidates = stockLocations.filter((loc) => loc.id !== fromPrimary)}
                {#if toCandidates.length === 0}
                  <p class="text-sm text-on-surface-variant">移動先として選べる棚がありません。</p>
                {:else}
                  <div class="rounded-2xl bg-surface-container-low p-4">
                    <div class="mb-4 flex flex-wrap gap-2">
                      {#each getSelectedToLabels() as label}
                        <span class="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">{label}</span>
                      {/each}
                    </div>
                    <div class="grid max-h-64 grid-cols-2 gap-2 overflow-y-auto md:grid-cols-3">
                      {#each toCandidates as loc}
                        <label
                          class="flex cursor-pointer items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold transition-colors {isLocationToSelected(loc.id)
                            ? 'bg-primary/10 text-on-surface'
                            : 'bg-surface-container text-on-surface hover:bg-surface-container-high'}"
                        >
                          <input
                            type="checkbox"
                            bind:group={locationToIds}
                            value={String(loc.id)}
                            class="h-4 w-4 rounded border-outline-variant text-primary focus:ring-primary"
                          />
                          <span>{String(loc.name).trim()}</span>
                        </label>
                      {/each}
                    </div>
                  </div>
                {/if}
              {/if}
            </div>
          </div>

          <div class="space-y-6 border-y border-outline-variant/15 py-8">
            <div class="flex flex-col gap-3 rounded-2xl bg-surface-container-low p-3 md:flex-row md:items-center md:justify-between">
              <p class="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">入力方法</p>
              <div class="inline-flex rounded-full bg-surface-container p-1">
                <button
                  type="button"
                  onclick={() => setEntryMode('quantity')}
                  class="rounded-full px-5 py-2 text-sm font-semibold transition-colors {entryMode === 'quantity'
                    ? 'bg-primary text-on-primary'
                    : 'text-on-surface-variant hover:text-on-surface'}"
                >
                  本数入力
                </button>
                <button
                  type="button"
                  onclick={() => setEntryMode('weight')}
                  class="rounded-full px-5 py-2 text-sm font-semibold transition-colors {entryMode === 'weight'
                    ? 'bg-primary text-on-primary'
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
                    >数量（本）</label
                  >
                  {#if entryMode === 'quantity'}
                    <div class="inline-flex rounded-full bg-surface-container p-1">
                      <button
                        type="button"
                        onclick={() => setQuantityStep(1)}
                        class="rounded-full px-3 py-1 text-xs font-semibold transition-colors {quantityStep === 1
                          ? 'bg-primary text-on-primary'
                          : 'text-on-surface-variant hover:text-on-surface'}"
                      >
                        1本
                      </button>
                      <button
                        type="button"
                        onclick={() => setQuantityStep(10)}
                        class="rounded-full px-3 py-1 text-xs font-semibold transition-colors {quantityStep === 10
                          ? 'bg-primary text-on-primary'
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

          <div class="pt-4 border-t border-outline-variant/10 flex items-center justify-between gap-6">
            <div class="flex items-center gap-2 text-on-surface-variant">
              <span class="material-symbols-outlined text-sm">schedule</span>
              <span class="text-xs font-medium">{formatDate(new Date())}</span>
            </div>
            <button
              type="submit"
              disabled={submitting || !canSubmit()}
              class="px-12 py-4 rounded-lg bg-primary text-on-primary font-semibold text-sm shadow-sm hover:opacity-90 active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {#if submitting}
                <span class="material-symbols-outlined animate-spin">progress_activity</span>
              {:else}
                <span class="material-symbols-outlined">swap_horiz</span>
              {/if}
              移動を記録
            </button>
          </div>
        </form>
      </div>
    </div>
  </main>
{/if}
