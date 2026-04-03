<script>
  import { fetchTransactions, deleteTransaction } from '$lib/api';
  import PaginationBar from '$lib/PaginationBar.svelte';
  import { maxPageIndex, SEARCH_DEBOUNCE_MS } from '$lib/pagination.js';

  const PAGE_SIZE = 25;

  let transactions = $state([]);
  let totalCount = $state(0);
  let loading = $state(true);
  let error = $state('');
  let filterType = $state('');
  let searchInput = $state('');
  let searchDebounced = $state('');
  let page = $state(1);
  let deletingId = $state(null);
  let loadVersion = 0;

  $effect(() => {
    searchInput;
    const t = setTimeout(() => {
      searchDebounced = searchInput;
      page = 1;
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  });

  async function loadTransactions() {
    const currentVersion = ++loadVersion;
    try {
      loading = true;
      error = '';
      const offset = (page - 1) * PAGE_SIZE;
      const { items, total } = await fetchTransactions({
        type: filterType || undefined,
        limit: PAGE_SIZE,
        offset,
        q: searchDebounced.trim() || undefined,
      });
      if (currentVersion !== loadVersion) return;
      transactions = items;
      totalCount = total;
      const cap = maxPageIndex(total, PAGE_SIZE);
      if (page > cap) page = cap;
    } catch (e) {
      if (currentVersion !== loadVersion) return;
      error = e?.message || '履歴の取得に失敗しました';
      console.error(e);
    } finally {
      if (currentVersion === loadVersion) loading = false;
    }
  }

  $effect(() => {
    filterType;
    searchDebounced;
    page;
    loadTransactions();
  });

  async function handleDelete(id) {
    if (deletingId !== null) return;
    if (!confirm('このトランザクションを削除しますか？')) return;
    deletingId = id;
    try {
      await deleteTransaction(id);
      await loadTransactions();
    } catch (e) {
      console.error(e);
      alert('削除に失敗しました');
    } finally {
      deletingId = null;
    }
  }

  function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('ja-JP', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
  }

  function formatTime(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleTimeString('ja-JP', {
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  function groupByDate(txList) {
    const groups = {};
    for (const tx of txList) {
      const dateKey = formatDate(tx.created_at);
      if (!groups[dateKey]) groups[dateKey] = [];
      groups[dateKey].push(tx);
    }
    return groups;
  }

  function getTypeIcon(type) {
    const icons = {
      in: 'south_west',
      out: 'north_east',
      return: 'assignment_return',
      adjust: 'tune',
      transfer: 'swap_horiz',
    };
    return icons[type] || 'swap_horiz';
  }

  function getTypeColor(type) {
    const colors = {
      in: 'text-primary',
      out: 'text-error',
      return: 'text-secondary',
      adjust: 'text-tertiary',
      transfer: 'text-on-surface',
    };
    return colors[type] || 'text-on-surface';
  }

  function getTypeBg(type) {
    const colors = {
      in: 'bg-primary/10 text-primary',
      out: 'bg-error/10 text-error',
      return: 'bg-secondary-container text-on-secondary-container',
      adjust: 'bg-tertiary-container/30 text-on-tertiary-container',
      transfer: 'bg-surface-container-highest text-on-surface',
    };
    return colors[type] || 'bg-surface-container text-on-surface';
  }

  function getTypeLabel(type) {
    const labels = {
      in: '入庫',
      out: '出庫',
      return: '戻し',
      adjust: '修正',
      transfer: '移動',
    };
    return labels[type] || type;
  }

  /** @param {import('$lib/api').Transaction} tx */
  function formatLocationLine(tx) {
    if (tx.type === 'transfer') {
      const from = tx.location_from_name || '—';
      const to = tx.location_to_name || '—';
      return `棚番 ${from} → 棚番 ${to}`;
    }
    if (tx.location_name) {
      return `棚番 ${tx.location_name}`;
    }
    return '';
  }

  const groupedTransactions = $derived(groupByDate(transactions));
</script>

<main class="max-w-5xl mx-auto px-8 mt-16 pb-32">
  <!-- Header -->
  <section class="mb-12">
    <h2 class="font-headline text-4xl font-bold tracking-tight text-on-surface mb-2">取引履歴</h2>
  </section>

  <!-- Search & Filter -->
  <section class="mb-6 flex flex-col gap-4">
    <div class="relative w-full md:max-w-md">
      <span
        class="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant text-sm"
        >search</span
      >
      <input
        type="text"
        bind:value={searchInput}
        placeholder="メモ・ロットコード・取引IDで検索"
        class="w-full bg-surface-container-low border-none rounded-xl py-3 pl-12 pr-4 focus:ring-1 focus:ring-primary/40 font-body text-sm placeholder:text-outline-variant"
      />
    </div>
    <div class="flex gap-2 overflow-x-auto w-full pb-2 md:pb-0">
      <button
        onclick={() => {
          filterType = '';
          page = 1;
        }}
        class="px-4 py-2 rounded-xl font-label text-xs font-semibold whitespace-nowrap transition-colors {!filterType
          ? 'bg-surface-container-highest text-on-secondary-container'
          : 'bg-surface-container-low text-on-surface-variant hover:bg-surface-container-highest'}"
      >
        すべて
      </button>
      <button
        onclick={() => {
          filterType = 'in';
          page = 1;
        }}
        class="px-4 py-2 rounded-xl font-label text-xs font-semibold whitespace-nowrap transition-colors {filterType ===
        'in'
          ? 'bg-primary/10 text-primary'
          : 'bg-surface-container-low text-on-surface-variant hover:bg-surface-container-highest'}"
      >
        入庫
      </button>
      <button
        onclick={() => {
          filterType = 'out';
          page = 1;
        }}
        class="px-4 py-2 rounded-xl font-label text-xs font-semibold whitespace-nowrap transition-colors {filterType ===
        'out'
          ? 'bg-error/10 text-error'
          : 'bg-surface-container-low text-on-surface-variant hover:bg-surface-container-highest'}"
      >
        出庫
      </button>
      <button
        onclick={() => {
          filterType = 'return';
          page = 1;
        }}
        class="px-4 py-2 rounded-xl font-label text-xs font-semibold whitespace-nowrap transition-colors {filterType ===
        'return'
          ? 'bg-secondary-container text-on-secondary-container'
          : 'bg-surface-container-low text-on-surface-variant hover:bg-surface-container-highest'}"
      >
        戻し
      </button>
      <button
        onclick={() => {
          filterType = 'transfer';
          page = 1;
        }}
        class="px-4 py-2 rounded-xl font-label text-xs font-semibold whitespace-nowrap transition-colors {filterType ===
        'transfer'
          ? 'bg-surface-container-highest text-on-surface'
          : 'bg-surface-container-low text-on-surface-variant hover:bg-surface-container-highest'}"
      >
        移動
      </button>
    </div>

    <PaginationBar bind:page total={totalCount} pageSize={PAGE_SIZE} disabled={loading} />
  </section>

  <!-- Transaction List -->
  {#if loading}
    <div class="flex items-center justify-center py-20">
      <span class="material-symbols-outlined text-4xl animate-spin">progress_activity</span>
    </div>
  {:else if error}
    <div class="rounded-xl border border-error/20 bg-error/10 p-6 text-on-surface">
      <p class="font-semibold text-error mb-2">履歴の読み込みに失敗しました</p>
      <p class="text-sm text-on-surface-variant">{error}</p>
      <button
        type="button"
        onclick={loadTransactions}
        class="mt-4 px-4 py-2 rounded-lg bg-surface-container-high text-on-surface text-sm font-semibold"
      >
        再試行
      </button>
    </div>
  {:else if totalCount === 0}
    <div class="text-center py-20 text-on-surface-variant">
      <span class="material-symbols-outlined text-6xl mb-4 opacity-20">history</span>
      <p class="font-serif italic">該当する履歴がありません</p>
    </div>
  {:else}
    <div class="space-y-6">
      {#each Object.entries(groupedTransactions) as [date, txs]}
        <!-- Date Header -->
        <div class="pt-4 pb-2">
          <h3 class="font-label text-[11px] uppercase tracking-widest text-outline font-bold">{date}</h3>
        </div>
        <!-- Transactions -->
        {#each txs as tx}
          <div
            class="group flex flex-col md:flex-row md:items-center justify-between p-6 bg-surface-container-lowest rounded-xl hover:bg-surface-container transition-all duration-300"
          >
            <div class="flex items-center gap-6">
              <div
                class="flex items-center justify-center w-12 h-12 rounded-full {getTypeBg(tx.type)}"
              >
                <span class="material-symbols-outlined">{getTypeIcon(tx.type)}</span>
              </div>
              <div>
                <div class="flex items-center gap-2 mb-1">
                  <span class="font-label text-[10px] font-bold uppercase tracking-tighter {getTypeBg(tx.type)} px-2 py-0.5 rounded"
                    >{getTypeLabel(tx.type)}</span
                  >
                  <span class="font-body text-xs text-on-surface-variant">{formatTime(tx.created_at)}</span>
                  <span class="font-mono text-[10px] text-outline-variant">#{tx.id}</span>
                </div>
                <p class="font-body text-on-surface">{tx.memo || 'メモなし'}</p>
                <p class="mt-1 text-xs text-on-surface-variant">{tx.lot_code || 'ロット不明'}</p>
                {#if formatLocationLine(tx)}
                  <p class="mt-1 text-xs text-on-surface-variant">{formatLocationLine(tx)}</p>
                {/if}
              </div>
            </div>
            <div class="mt-4 md:mt-0 flex items-center gap-12 text-right">
              <div class="flex flex-col">
                <span class="font-label text-[11px] text-on-surface-variant uppercase">数量</span>
                <span class="font-headline text-xl text-on-surface">
                  {#if tx.type === 'transfer'}
                    {tx.quantity}
                  {:else if tx.type === 'in' || tx.type === 'return'}
                    + {tx.quantity}
                  {:else}
                    - {tx.quantity}
                  {/if}
                </span>
              </div>
              <div class="flex flex-col">
                <span class="font-label text-[11px] text-on-surface-variant uppercase">重量</span>
                <span class="font-headline text-xl text-on-surface">
                  {tx.weight.toFixed(1)} <span class="text-xs font-sans text-outline">kg</span>
                </span>
              </div>
              <button
                onclick={() => handleDelete(tx.id)}
                disabled={deletingId === tx.id}
                class="p-2 rounded-lg text-on-surface-variant hover:bg-error/10 hover:text-error transition-colors opacity-0 group-hover:opacity-100"
                title="削除"
              >
                <span class="material-symbols-outlined">delete</span>
              </button>
            </div>
          </div>
        {/each}
      {/each}
    </div>
  {/if}
</main>
