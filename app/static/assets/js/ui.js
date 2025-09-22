(function () {
  const tabGroups = new Map();

  function initTabs() {
    document.querySelectorAll('.tablist').forEach((tablist, index) => {
      const groupId = tablist.dataset.tabGroup || `tab-group-${index}`;
      tablist.dataset.tabGroup = groupId;
      const tabs = Array.from(tablist.querySelectorAll('[role="tab"]'));
      const panels = tabs
        .map((tab) => {
          const panelId = tab.getAttribute('aria-controls');
          return panelId ? document.getElementById(panelId) : null;
        })
        .filter(Boolean);

      tabs.forEach((tab) => {
        tab.setAttribute('tabindex', tab.classList.contains('active') ? '0' : '-1');
        tab.setAttribute('aria-selected', tab.classList.contains('active') ? 'true' : 'false');
        tab.addEventListener('click', () => activateTab(groupId, tab.id));
        tab.addEventListener('keydown', (event) => handleTabKeydown(event, groupId));
      });

      panels.forEach((panel) => {
        if (!panel) return;
        panel.setAttribute('tabindex', '0');
      });

      tabGroups.set(groupId, { tabs, panels });
    });
  }

  function handleTabKeydown(event, groupId) {
    const group = tabGroups.get(groupId);
    if (!group) return;

    const { tabs } = group;
    const currentIndex = tabs.findIndex((tab) => tab.id === event.target.id);
    if (currentIndex === -1) return;

    let nextIndex = currentIndex;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      nextIndex = (currentIndex + 1) % tabs.length;
      event.preventDefault();
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
      event.preventDefault();
    }

    if (nextIndex !== currentIndex) {
      activateTab(groupId, tabs[nextIndex].id);
      tabs[nextIndex].focus();
    }
  }

  function activateTab(groupId, tabId) {
    const group = tabGroups.get(groupId);
    if (!group) return;
    const { tabs } = group;

    tabs.forEach((tab) => {
      const controls = tab.getAttribute('aria-controls');
      const panel = controls ? document.getElementById(controls) : null;
      const isActive = tab.id === tabId;
      tab.classList.toggle('active', isActive);
      tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
      tab.setAttribute('tabindex', isActive ? '0' : '-1');
      if (panel) {
        panel.classList.toggle('active', isActive);
        if (isActive) {
          panel.removeAttribute('hidden');
        } else {
          panel.setAttribute('hidden', 'true');
        }
      }
    });
  }

  async function copyToClipboard(button, targetId) {
    const target = document.getElementById(targetId);
    if (!target) return;
    const text = 'value' in target ? target.value : target.textContent || '';
    try {
      await navigator.clipboard.writeText(text.trim());
      flashButtonState(button, 'Copied');
    } catch (error) {
      console.error('Copy failed', error);
      flashButtonState(button, 'Copy failed');
    }
  }

  function downloadContent(targetId, filename) {
    const target = document.getElementById(targetId);
    if (!target) return;
    const text = 'value' in target ? target.value : target.textContent || '';
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  function flashButtonState(button, message) {
    if (!button) return;
    const original = button.textContent;
    button.textContent = message;
    button.disabled = true;
    setTimeout(() => {
      button.textContent = original;
      button.disabled = false;
    }, 1600);
  }

  function initCopyButtons() {
    document.querySelectorAll('[data-copy-target]').forEach((button) => {
      button.addEventListener('click', () => copyToClipboard(button, button.dataset.copyTarget));
    });
  }

  function initDownloadButtons() {
    document.querySelectorAll('[data-download]').forEach((button) => {
      button.addEventListener('click', () => {
        const target = button.dataset.downloadTarget;
        const filename = button.dataset.download || 'download.txt';
        if (target) {
          downloadContent(target, filename);
        }
      });
    });
  }

  function updateYear() {
    const year = String(new Date().getFullYear());
    document.querySelectorAll('[data-year]').forEach((element) => {
      element.textContent = year;
    });
  }

  function init() {
    initTabs();
    initCopyButtons();
    initDownloadButtons();
    updateYear();
  }

  document.addEventListener('DOMContentLoaded', init);

  window.LAWAgentUI = {
    activateTab(groupId, tabId) {
      activateTab(groupId, tabId);
    },
  };
})();
