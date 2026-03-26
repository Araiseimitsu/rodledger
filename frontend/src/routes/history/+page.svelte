<script>
  import { fetchTransactions, deleteTransaction } from '$lib/api';

  let transactions = $state([]);
  let loading = $state(true);
  let error = $state('');
  let filterType = $state('');
  let searchQuery = $state('');
  let deletingId = $state(null);
  let loadVersion = 0;

  async function loadTransactions() {
    const currentVersion = ++loadVersion;
    try {
      loading = true;
      error = '';
      transactions = await fetchTransactions({
        type: filterType || undefined,
        limit: 100,
      });
    } catch (e) {
      if (currentVersion !== loadVersion) return;
      error = e?.message || '履歴の取得に失敗しました';
      console.error(e);
    } finally {
      if (currentVersion !== loadVersion) return;
      loading = false;
    }
  }

  $effect(() => {
    filterType;
    loadTransactions();
  });

  async function handleDelete(id) {
    if (deletingId !== null) return;
    if (!confirm('このトランザクションを削除しますか？')) return;
    deletingId = id;
    try {
      await deleteTransaction(id);
      transactions = transactions.filter((t) => t.id !== id);
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

  function getTypeBg(type) {
    const colors = {
      in: 'bg-primary/10 text-primary',
      out: 'bg-error/10 text-error',
      return: 'bg-secondary-container text-on-secondary-container',
      adjust: 'bg-tertiary-container/30 text-on-tertiary-container',
    };
    return colors[type] || 'bg-surface-container text-on-surface';
  }

  function getTypeLabel(type) {
    const labels = {
      in: '入庫',
      out: '出庫',
      return: '戻し',
      adjust: '修正',
    };
    return labels[type] || type;
  }

  const filtered = $derived(
    searchQuery
      ? transactions.filter((t) => t.memo?.toLowerCase().includes(searchQuery.toLowerCase()))
      : transactions
  );

  const groupedTransactions = $derived(groupByDate(filtered));
</script>

<main class="max-w-5xl mx-auto px-8 mt-16 pb-32">
  <!-- Header -->
  <section class="mb-12">
    <h2 class="font-headline text-4xl font-bold tracking-tight text-on-surface mb-2">取引履歴</h2>
    <p class="font-body text-on-surface-variant max-w-lg">材料の移動履歴と在庫調整の記録。</p>
  </section>

  <!-- Search & Filter -->
  <section class="mb-10 flex flex-col md:flex-row gap-4 items-center">
    <div class="relative w-full md:w-96">
      <span
        class="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant text-sm"
        >search</span
      >
      <input
        type="text"
        bind:value={searchQuery}
        placeholder="検索..."
        class="w-full bg-surface-container-low border-none rounded-xl py-3 pl-12 pr-4 focus:ring-1 focus:ring-primary/40 font-body text-sm placeholder:text-outline-variant"
      />
    </div>
    <div class="flex gap-2 overflow-x-auto w-full md:w-auto pb-2 md:pb-0">
      <button
        onclick={() => (filterType = '')}
        class="px-4 py-2 rounded-xl font-label text-xs font-semibold whitespace-nowrap transition-colors {!filterType
          ? 'bg-surface-container-highest text-on-secondary-container'
          : 'bg-surface-container-low text-on-surface-variant hover:bg-surface-container-highest'}"
      >
        すべて
      </button>
      <button
        onclick={() => (filterType = 'in')}
        class="px-4 py-2 rounded-xl font-label text-xs font-semibold whitespace-nowrap transition-colors {filterType ===
        'in'
          ? 'bg-primary/10 text-primary'
          : 'bg-surface-container-low text-on-surface-variant hover:bg-surface-container-highest'}"
      >
        入庫
      </button>
      <button
        onclick={() => (filterType = 'out')}
        class="px-4 py-2 rounded-xl font-label text-xs font-semibold whitespace-nowrap transition-colors {filterType ===
        'out'
          ? 'bg-error/10 text-error'
          : 'bg-surface-container-low text-on-surface-variant hover:bg-surface-container-highest'}"
      >
        出庫
      </button>
      <button
        onclick={() => (filterType = 'return')}
        class="px-4 py-2 rounded-xl font-label text-xs font-semibold whitespace-nowrap transition-colors {filterType ===
        'return'
          ? 'bg-secondary-container text-on-secondary-container'
          : 'bg-surface-container-low text-on-surface-variant hover:bg-surface-container-highest'}"
      >
        戻し
      </button>
    </div>
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
  {:else if Object.keys(groupedTransactions).length === 0}
    <div class="text-center py-20 text-on-surface-variant">
      <span class="material-symbols-outlined text-6xl mb-4 opacity-20">history</span>
      <p class="font-serif italic">履歴がありません</p>
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
                </div>
                <p class="font-body text-on-surface">{tx.memo || 'メモなし'}</p>
              </div>
            </div>
            <div class="mt-4 md:mt-0 flex items-center gap-12 text-right">
              <div class="flex flex-col">
                <span class="font-label text-[11px] text-on-surface-variant uppercase">数量</span>
                <span class="font-headline text-xl text-on-surface">
                  {tx.type === 'in' || tx.type === 'return' ? '+' : '-'} {tx.quantity}
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
