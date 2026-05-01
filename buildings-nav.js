(function () {
  const linkGroups = Array.from(document.querySelectorAll('.buildings-quick-links'));
  if (!linkGroups.length) return;

  const parseLinkUrl = (link) => {
    const href = link && link.getAttribute('href');
    if (!href) return null;
    try {
      return new URL(href, window.location.href);
    } catch (error) {
      return null;
    }
  };

  const syncGroupState = (group) => {
    const links = Array.from(group.querySelectorAll('.buildings-quick-link'));
    if (!links.length) return;

    links.forEach((link) => link.removeAttribute('aria-current'));

    const currentPath = window.location.pathname;
    const currentHash = window.location.hash || '';
    let activeLink = null;

    links.forEach((link) => {
      const url = parseLinkUrl(link);
      if (!url || url.pathname !== currentPath) return;

      if (url.hash) {
        if (url.hash === currentHash) activeLink = link;
        return;
      }

      if (!currentHash && !activeLink) activeLink = link;
    });

    if (!activeLink) {
      activeLink = links.find((link) => {
        const url = parseLinkUrl(link);
        return url && url.pathname === currentPath && !url.hash;
      }) || null;
    }

    if (!activeLink) return;
    activeLink.setAttribute('aria-current', 'page');
  };

  const syncAllGroups = () => {
    linkGroups.forEach(syncGroupState);
  };

  linkGroups.forEach((group) => {
    group.addEventListener('click', (event) => {
      const link = event.target instanceof Element
        ? event.target.closest('.buildings-quick-link')
        : null;
      if (!link || !group.contains(link)) return;
      window.requestAnimationFrame(syncAllGroups);
    });
  });

  window.addEventListener('hashchange', syncAllGroups);
  syncAllGroups();
})();
