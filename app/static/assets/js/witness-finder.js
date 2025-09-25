(function () {
  const form = document.getElementById('witnessFinderForm');
  const submitBtn = document.getElementById('wfSubmitBtn');
  const errorEl = form ? form.querySelector('.form-error') : null;
  const loadingEl = document.getElementById('wfLoading');
  const progressEl = document.getElementById('wfProgress');
  const progressBarEl = document.getElementById('wfProgressBar');
  const etaEl = document.getElementById('wfEta');
  const resultsEl = document.getElementById('wfResults');
  const emptyEl = document.getElementById('wfEmpty');
  const statusEl = document.getElementById('wfResultsStatus');
  const savedListEl = document.getElementById('wfSavedList');
  const savedEmptyEl = document.getElementById('wfSavedEmpty');
  const toggleSavedBtn = document.getElementById('wfToggleSaved');
  const toastContainer = document.querySelector('.toast-container');

  const filterSimilarity = document.getElementById('filterSimilarity');
  const filterExperience = document.getElementById('filterExperience');
  const filterSector = document.getElementById('filterSector');
  const filterLocation = document.getElementById('filterLocation');

  const state = {
    loading: false,
    progressTimer: null,
    etaTimer: null,
    results: [],
    filtered: [],
    saved: new Map(),
  };

  function showToast(message) {
    if (!toastContainer) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.classList.add('fade-out');
      toast.addEventListener('transitionend', () => toast.remove(), { once: true });
    }, 2400);
  }

  function updateFilterDisplay() {
    const similarityDisplay = document.querySelector('[data-filter-display="similarity"]');
    const experienceDisplay = document.querySelector('[data-filter-display="experience"]');
    if (similarityDisplay) similarityDisplay.textContent = `${filterSimilarity.value}%`;
    if (experienceDisplay) experienceDisplay.textContent = `${filterExperience.value}`;
  }

  function startLoading() {
    if (!form || !loadingEl) return;
    state.loading = true;
    form.hidden = true;
    loadingEl.hidden = false;
    submitBtn.disabled = true;
    if (errorEl) {
      errorEl.hidden = true;
      errorEl.textContent = '';
    }

    let progress = 0;
    let eta = 6;
    if (progressEl) progressEl.textContent = '0%';
    if (etaEl) etaEl.textContent = String(eta).padStart(2, '0');
    if (progressBarEl) progressBarEl.style.width = '0%';

    const segments = [
      { target: 60, duration: 1200 },
      { target: 85, duration: 2000 },
      { target: 98, duration: 3000 },
    ];
    let currentSegment = 0;
    let segmentStart = performance.now();

    function tick(now) {
      if (!state.loading) return;
      const segment = segments[currentSegment];
      if (!segment) return;
      const elapsed = now - segmentStart;
      const fraction = Math.min(1, elapsed / segment.duration);
      const segmentProgress = progress + (segment.target - progress) * fraction;
      if (progressEl) progressEl.textContent = `${Math.floor(segmentProgress)}%`;
      if (progressBarEl) progressBarEl.style.width = `${segmentProgress}%`;
      if (fraction >= 1 && currentSegment < segments.length - 1) {
        progress = segment.target;
        currentSegment += 1;
        segmentStart = now;
      }
      state.progressTimer = requestAnimationFrame(tick);
    }

    state.progressTimer = requestAnimationFrame(tick);

    state.etaTimer = setInterval(() => {
      if (!state.loading) return;
      eta = Math.max(0, eta - 1);
      if (etaEl) etaEl.textContent = String(eta).padStart(2, '0');
    }, 1000);
  }

  function stopLoading(success) {
    state.loading = false;
    submitBtn.disabled = false;
    if (state.progressTimer) cancelAnimationFrame(state.progressTimer);
    if (state.etaTimer) clearInterval(state.etaTimer);
    if (progressEl) progressEl.textContent = '100%';
    if (progressBarEl) progressBarEl.style.width = '100%';
    if (etaEl) etaEl.textContent = '00';

    setTimeout(() => {
      if (loadingEl) loadingEl.hidden = true;
      if (form) {
        form.hidden = false;
        const focusTarget = form.querySelector('input, textarea');
        if (!success && focusTarget) focusTarget.focus();
      }
    }, 400);
  }

  function renderEmptyState() {
    if (!emptyEl) return;
    const showEmpty = state.results.length > 0 && state.filtered.length === 0;
    emptyEl.hidden = !showEmpty;
  }

  function createSkillBadges(skills) {
    if (!skills || !skills.length) return null;
    const container = document.createElement('div');
    container.className = 'witness-skills';
    skills.slice(0, 8).forEach((skill) => {
      const badge = document.createElement('span');
      badge.className = 'badge';
      badge.textContent = skill;
      container.appendChild(badge);
    });
    return container;
  }

  function createLinksSection(candidate) {
    const links = document.createElement('div');
    links.className = 'witness-links';
    const primaryLinks = candidate.links && candidate.links.length ? candidate.links : [];
    const sourceLinks = (candidate.sources || []).map((source) => source.url);
    const combined = [...new Set([...primaryLinks, ...sourceLinks])].slice(0, 6);
    if (!combined.length) return null;
    combined.forEach((url) => {
      if (!url) return;
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.target = '_blank';
      anchor.rel = 'noopener noreferrer';
      anchor.textContent = url;
      links.appendChild(anchor);
    });
    return links;
  }

  function copyCandidate(candidate) {
    const text = [
      `Name: ${candidate.name}`,
      candidate.title ? `Title: ${candidate.title}` : '',
      candidate.organization ? `Organization: ${candidate.organization}` : '',
      candidate.sector ? `Sector: ${candidate.sector}` : '',
      candidate.location ? `Location: ${candidate.location}` : '',
      Number.isFinite(candidate.years_experience)
        ? `Years experience: ${candidate.years_experience}`
        : '',
      `Similarity: ${candidate.similarity_score}%`,
      candidate.summary ? `Summary: ${candidate.summary}` : '',
      candidate.skills && candidate.skills.length ? `Skills: ${candidate.skills.join(', ')}` : '',
      candidate.links && candidate.links.length ? `Links: ${candidate.links.join(', ')}` : '',
    ]
      .filter(Boolean)
      .join('\n');

    navigator.clipboard
      .writeText(text)
      .then(() => showToast('Candidate copied.'))
      .catch(() => showToast('Unable to copy candidate.'));
  }

  function openSources(candidate) {
    const links = (candidate.sources || []).map((source) => source.url).filter(Boolean);
    if (!links.length) {
      showToast('No sources available for this candidate.');
      return;
    }
    links.slice(0, 4).forEach((url, index) => {
      setTimeout(() => window.open(url, '_blank', 'noopener'), index * 150);
    });
  }

  function renderResults() {
    if (!resultsEl) return;
    resultsEl.innerHTML = '';
    state.filtered.forEach((candidate) => {
      const card = document.createElement('article');
      card.className = 'witness-card';
      card.dataset.id = candidate.id;

      const header = document.createElement('div');
      header.className = 'witness-card-header';
      const title = document.createElement('h3');
      title.textContent = candidate.name;
      const score = document.createElement('span');
      score.className = 'witness-score';
      score.textContent = `${candidate.similarity_score}% match`;
      header.append(title, score);

      const meta = document.createElement('p');
      meta.className = 'witness-meta';
      const parts = [];
      if (candidate.title) parts.push(candidate.title);
      if (candidate.organization) parts.push(candidate.organization);
      if (candidate.sector) parts.push(candidate.sector);
      if (Number.isFinite(candidate.years_experience)) {
        parts.push(`${candidate.years_experience} yrs exp.`);
      }
      if (candidate.location) parts.push(candidate.location);
      meta.textContent = parts.join(' · ');

      const summary = document.createElement('p');
      summary.className = 'witness-summary';
      summary.textContent = candidate.summary || 'No summary available.';

      const skillBadges = createSkillBadges(candidate.skills);
      const actions = document.createElement('div');
      actions.className = 'witness-actions';

      const saveBtn = document.createElement('button');
      saveBtn.type = 'button';
      saveBtn.className = 'btn ghost';
      const isSaved = state.saved.has(candidate.id);
      saveBtn.textContent = isSaved ? 'Saved' : 'Save';
      saveBtn.disabled = isSaved;
      saveBtn.addEventListener('click', () => handleSave(candidate, saveBtn));

      const copyBtn = document.createElement('button');
      copyBtn.type = 'button';
      copyBtn.className = 'btn ghost';
      copyBtn.textContent = 'Copy';
      copyBtn.addEventListener('click', () => copyCandidate(candidate));

      const sourceBtn = document.createElement('button');
      sourceBtn.type = 'button';
      sourceBtn.className = 'btn ghost';
      sourceBtn.textContent = 'Open Sources';
      sourceBtn.addEventListener('click', () => openSources(candidate));

      actions.append(saveBtn, copyBtn, sourceBtn);

      card.append(header, meta, summary);
      if (skillBadges) card.appendChild(skillBadges);
      card.appendChild(actions);

      const linksSection = createLinksSection(candidate);
      if (linksSection) card.appendChild(linksSection);

      resultsEl.appendChild(card);
    });

    renderEmptyState();
  }

  function applyFilters() {
    const minSimilarity = Number(filterSimilarity.value || 0);
    const minExperience = Number(filterExperience.value || 0);
    const sectorQuery = filterSector.value.trim().toLowerCase();
    const locationQuery = filterLocation.value.trim().toLowerCase();

    state.filtered = state.results.filter((candidate) => {
      if (candidate.similarity_score < minSimilarity) return false;
      const years = Number(candidate.years_experience || 0);
      if (years < minExperience) return false;
      if (sectorQuery && !(candidate.sector || '').toLowerCase().includes(sectorQuery)) return false;
      if (locationQuery && !(candidate.location || '').toLowerCase().includes(locationQuery)) return false;
      return true;
    });

    renderResults();
  }

  async function handleSave(candidate, button) {
    try {
      const response = await fetch('/api/witness_finder/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ candidate }),
      });
      if (!response.ok) throw new Error('Failed to save');
      const data = await response.json();
      state.saved.set(candidate.id, candidate);
      if (data.status === 'duplicate') {
        showToast('Already saved.');
      } else {
        showToast('Candidate saved.');
      }
      if (button) {
        button.textContent = 'Saved';
        button.disabled = true;
      }
      renderSaved();
    } catch (error) {
      console.error(error);
      showToast('Unable to save candidate.');
    }
  }

  async function handleDelete(candidateId) {
    try {
      const response = await fetch(`/api/witness_finder/saved/${encodeURIComponent(candidateId)}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error('Failed to delete');
      const data = await response.json();
      if (data.status === 'ok') {
        state.saved.delete(candidateId);
        showToast('Removed from saved.');
        renderSaved();
        applyFilters();
      }
    } catch (error) {
      console.error(error);
      showToast('Unable to remove candidate.');
    }
  }

  function renderSaved() {
    if (!savedListEl || !savedEmptyEl) return;
    savedListEl.innerHTML = '';
    const savedValues = Array.from(state.saved.values());
    if (!savedValues.length) {
      savedEmptyEl.hidden = false;
      savedListEl.hidden = true;
      return;
    }
    savedEmptyEl.hidden = true;
    savedListEl.hidden = toggleSavedBtn.getAttribute('aria-expanded') !== 'true';

    savedValues.forEach((candidate) => {
      const card = document.createElement('article');
      card.className = 'saved-card';
      const header = document.createElement('header');
      const title = document.createElement('h3');
      title.textContent = candidate.name;
      const actions = document.createElement('div');
      actions.className = 'saved-card-actions';
      const copyBtn = document.createElement('button');
      copyBtn.type = 'button';
      copyBtn.className = 'btn ghost';
      copyBtn.textContent = 'Copy';
      copyBtn.addEventListener('click', () => copyCandidate(candidate));
      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'btn ghost';
      removeBtn.textContent = 'Remove';
      removeBtn.addEventListener('click', () => handleDelete(candidate.id));
      actions.append(copyBtn, removeBtn);
      header.append(title, actions);

      const meta = document.createElement('p');
      meta.className = 'witness-meta';
      meta.textContent = [candidate.title, candidate.organization, candidate.location]
        .filter(Boolean)
        .join(' · ');

      const summary = document.createElement('p');
      summary.className = 'witness-summary';
      summary.textContent = candidate.summary || 'No summary provided.';

      card.append(header, meta, summary);
      savedListEl.appendChild(card);
    });
  }

  async function fetchSaved() {
    try {
      const response = await fetch('/api/witness_finder/saved');
      if (!response.ok) throw new Error('Failed to fetch saved');
      const data = await response.json();
      if (Array.isArray(data)) {
        data.forEach((candidate) => {
          if (candidate && candidate.id) state.saved.set(candidate.id, candidate);
        });
      }
      renderSaved();
    } catch (error) {
      console.error(error);
    }
  }

  function handleFilters() {
    updateFilterDisplay();
    applyFilters();
  }

  async function performSearch(payload) {
    try {
      const response = await fetch('/api/witness_finder/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Search failed.');
      }
      return response.json();
    } catch (error) {
      throw error;
    }
  }

  function updateStatus(message) {
    if (statusEl) statusEl.textContent = message;
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (state.loading) return;
    const formData = new FormData(form);
    const industry = formData.get('industry').toString().trim();
    const description = formData.get('description').toString().trim();
    const name = formData.get('name').toString().trim();
    if (!industry || !description) {
      if (errorEl) {
        errorEl.hidden = false;
        errorEl.textContent = 'Industry and description are required.';
      }
      return;
    }

    const payload = { industry, description, limit: 8 };
    if (name) payload.name = name;

    startLoading();
    updateStatus('Searching the web for expert witnesses…');

    try {
      const data = await performSearch(payload);
      const candidates = Array.isArray(data?.candidates) ? data.candidates : [];
      state.results = candidates;
      applyFilters();
      if (candidates.length) {
        updateStatus(`Found ${candidates.length} candidate${candidates.length === 1 ? '' : 's'}.`);
      } else {
        updateStatus('No candidates returned. Try refining your query.');
      }
      candidates.forEach((candidate) => {
        if (state.saved.has(candidate.id)) return;
        // ensure we keep saved map up-to-date when reloading same candidate
      });
      stopLoading(true);
    } catch (error) {
      console.error(error);
      if (errorEl) {
        errorEl.hidden = false;
        errorEl.textContent = error.message || 'Search failed. Please try again.';
      }
      updateStatus('Search failed. Please try again.');
      stopLoading(false);
    }
  }

  function initFilters() {
    [filterSimilarity, filterExperience, filterSector, filterLocation].forEach((input) => {
      if (!input) return;
      const eventName = input.type === 'range' ? 'input' : 'keyup';
      input.addEventListener(eventName, handleFilters);
    });
    updateFilterDisplay();
  }

  function initSavedToggle() {
    if (!toggleSavedBtn || !savedListEl) return;
    toggleSavedBtn.addEventListener('click', () => {
      const expanded = toggleSavedBtn.getAttribute('aria-expanded') === 'true';
      toggleSavedBtn.setAttribute('aria-expanded', String(!expanded));
      toggleSavedBtn.textContent = expanded ? 'Show saved' : 'Hide saved';
      savedListEl.hidden = expanded;
    });
  }

  function init() {
    if (!form) return;
    form.addEventListener('submit', onSubmit);
    initFilters();
    initSavedToggle();
    fetchSaved();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
