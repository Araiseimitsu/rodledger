<svelte:head>
  <title>RodLedger β</title>
</svelte:head>

<script>
  import { goto } from '$app/navigation';
  import { page } from '$app/state';

  let { children } = $props();

  const currentPath = $derived(page.url.pathname);

  const navItems = [
    { path: '/', label: 'Home', icon: 'home' },
    { path: '/in', label: 'In', icon: 'south_west' },
    { path: '/out', label: 'Out', icon: 'north_east' },
    { path: '/transfer', label: 'Move', icon: 'swap_horiz' },
    { path: '/lots', label: 'Lots', icon: 'inventory_2' },
    { path: '/history', label: 'History', icon: 'history' },
  ];
</script>

<div class="min-h-screen pb-24">
  <!-- TopAppBar -->
  <header class="fixed top-0 w-full z-50 bg-background/70 backdrop-blur-2xl shadow-[0_12px_40px_rgba(43,52,55,0.06)]">
    <div class="flex items-center justify-between px-8 h-16 w-full">
      <div class="flex items-center gap-4">
        <button class="text-primary hover:bg-surface-container p-2 rounded-full transition-colors duration-300">
          <span class="material-symbols-outlined">menu</span>
        </button>
        <h1 class="font-serif italic text-xl text-on-background">RodLedger β</h1>
      </div>
      <nav class="hidden md:flex items-center gap-8">
        {#each navItems as item}
          <button
            onclick={() => goto(item.path)}
            class="px-3 py-1 rounded transition-colors duration-300 {currentPath === item.path
              ? 'text-primary font-semibold'
              : 'text-on-surface-variant hover:bg-surface-container'}"
          >
            {item.label}
          </button>
        {/each}
      </nav>
    </div>
  </header>

  <!-- Main Content -->
  <div class="pt-20">
    {@render children()}
  </div>

  <!-- BottomNavBar (Mobile) -->
  <nav class="md:hidden fixed bottom-0 left-0 w-full flex justify-around items-center h-20 px-6 bg-white/80 backdrop-blur-3xl z-50 rounded-t-xl border-t border-outline-variant/15 shadow-[0_-8px_30px_rgba(0,0,0,0.04)]">
    {#each navItems as item}
      <button
        onclick={() => goto(item.path)}
        class="flex flex-col items-center justify-center transition-all {currentPath === item.path
          ? 'text-primary scale-110'
          : 'text-on-surface-variant opacity-60 hover:opacity-100'}"
      >
        <span class="material-symbols-outlined">{item.icon}</span>
        <span class="text-xs font-medium tracking-wide mt-1">{item.label}</span>
      </button>
    {/each}
  </nav>
</div>
