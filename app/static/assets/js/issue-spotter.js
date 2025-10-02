(function () {
  document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('issueSpotterForm');
    if (!form) return;

    const fileInput = document.getElementById('fileInput');
    const textInput = document.getElementById('textInput');
    const instructionsInput = document.getElementById('instructionsInput');
    const styleSelect = document.getElementById('styleSelect');
    const returnJsonToggle = document.getElementById('returnJsonToggle');
    const submitBtn = document.getElementById('submitBtn');
    const errorEl = form.querySelector('.form-error');
    const statusEl = document.querySelector('.results-status');

    const summaryOutput = document.getElementById('summaryOutput');
    const findingsOutput = document.getElementById('findingsOutput');
    const citationsOutput = document.getElementById('citationsOutput');
    const jsonOutput = document.getElementById('jsonOutput');

    const followupInput = document.getElementById('followup-textarea');
    const followupBtn = document.getElementById('ask-followup-btn');
    const followupError = document.getElementById('followupError');
    const followupConversation = document.getElementById('followup-chat');

    const sessionSupported = supportsSessionStorage();
    const FOLLOWUP_STATE_KEY = 'lawagent:issue-spotter:followup-state';
    const THEME_STATE_KEY = 'lawagent:theme';
    const FOLLOWUP_TRANSCRIPT_LIMIT = 60;

    let latestAnalysisData = null;
    let latestInstructionText = '';
    let latestStyleSelection = '';
    let latestDocumentSource = '';
    let followupHistory = [];
    let followupTranscript = [];
    let pendingAnalysisMeta = null;

    const tabGroupId = 'results';

    restoreThemePreference();
    restoreFollowupState();

    if (followupBtn) {
      followupBtn.addEventListener('click', handleFollowupRequest);
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      clearError();
      clearFollowupError();

      const hasFile = fileInput.files && fileInput.files.length > 0;
      const textValue = textInput.value.trim();
      const instructionsValue = instructionsInput.value.trim();
      const styleValue = styleSelect.value;
      const wantsJson = returnJsonToggle.checked;

      if (!hasFile && !textValue) {
        showError('Upload a document or paste text to analyze.');
        fileInput.focus();
        return;
      }

      if (!instructionsValue) {
        showError('Instructions are required.');
        instructionsInput.focus();
        return;
      }

      pendingAnalysisMeta = {
        instructions: clampText(instructionsValue, 4000),
        style: styleValue || '',
        document: hasFile
          ? describeUploadedFile(fileInput.files[0])
          : clampText(textValue, 8000),
      };

      setLoading(true);
      updateStatus('Analyzing…');

      try {
        const response = await submitAnalysis({
          hasFile,
          instructionsValue,
          styleValue,
          wantsJson,
        });

        if (!response.ok) {
          const errorPayload = await safeJson(response);
          const detail = errorPayload?.detail || response.statusText || 'Analysis failed.';
          throw new Error(detail);
        }

        const data = await response.json();
        renderResults(data, { wantsJson });
        updateStatus('Analysis complete.');
        window.LAWAgentUI?.activateTab(tabGroupId, 'tab-summary');
      } catch (error) {
        console.error(error);
        updateStatus('Analysis failed.');
        showError(error.message || 'Unable to process the request.');
        pendingAnalysisMeta = null;
      } finally {
        setLoading(false);
      }
    });

    async function submitAnalysis({ hasFile, instructionsValue, styleValue, wantsJson }) {
      if (hasFile) {
        const formData = new FormData();
        formData.append('instructions', instructionsValue);
        formData.append('return_json', String(wantsJson));
        if (styleValue) {
          formData.append('style', styleValue);
        }
        const file = fileInput.files[0];
        formData.append('file', file);

        return fetch('/api/issue-spotter/upload', {
          method: 'POST',
          body: formData,
        });
      }

      const payload = {
        text: textInput.value.trim(),
        instructions: instructionsValue,
        style: styleValue || null,
        return_json: wantsJson,
      };

      return fetch('/api/issue-spotter/text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    }

    function renderResults(data, { wantsJson }) {
      const { summary, findings, citations, raw_json: rawJson } = data;
      latestAnalysisData = {
        summary: typeof summary === 'string' ? summary : '',
        findings: Array.isArray(findings) ? findings : [],
        citations: Array.isArray(citations) ? citations : [],
        raw_json: rawJson ?? null,
      };

      if (pendingAnalysisMeta) {
        latestInstructionText = pendingAnalysisMeta.instructions || '';
        latestStyleSelection = pendingAnalysisMeta.style || '';
        latestDocumentSource = pendingAnalysisMeta.document || '';
        pendingAnalysisMeta = null;
      } else {
        latestInstructionText = clampText(instructionsInput.value.trim(), 4000);
        latestStyleSelection = styleSelect.value || '';
        const textValue = textInput.value.trim();
        if (textValue) {
          latestDocumentSource = clampText(textValue, 8000);
        }
      }

      resetFollowupConversation();
      clearFollowupError();
      summaryOutput.textContent = (summary && summary.trim()) || 'No summary provided.';

      renderFindings(Array.isArray(findings) ? findings : []);
      renderCitations(Array.isArray(citations) ? citations : []);

      if (wantsJson) {
        try {
          jsonOutput.textContent = rawJson
            ? JSON.stringify(rawJson, null, 2)
            : JSON.stringify(data, null, 2);
        } catch (error) {
          console.error('Failed to format JSON', error);
          jsonOutput.textContent = 'Unable to display JSON payload.';
        }
      } else {
        jsonOutput.textContent = 'JSON output was disabled for this request.';
      }

      persistFollowupState();
    }

    function renderFindings(items) {
      findingsOutput.innerHTML = '';
      if (!items.length) {
        findingsOutput.innerHTML = '<p class="empty">No findings returned.</p>';
        return;
      }

      items.forEach((item, index) => {
        const finding = document.createElement('article');
        finding.className = 'finding';

        const heading = document.createElement('h3');
        heading.textContent = item.issue || `Finding ${index + 1}`;
        finding.appendChild(heading);

        if (item.risk) {
          const risk = document.createElement('p');
          risk.innerHTML = `<strong>Risk:</strong> ${escapeHtml(item.risk)}`;
          finding.appendChild(risk);
        }

        if (item.suggestion) {
          const suggestion = document.createElement('p');
          suggestion.innerHTML = `<strong>Suggestion:</strong> ${escapeHtml(item.suggestion)}`;
          finding.appendChild(suggestion);
        }

        if (item.span && (item.span.page || item.span.start || item.span.end)) {
          const span = document.createElement('p');
          const parts = [];
          if (item.span.page) parts.push(`Page ${item.span.page}`);
          if (item.span.start || item.span.end) {
            parts.push(`Chars ${item.span.start || '?'}-${item.span.end || '?'}`);
          }
          span.innerHTML = `<strong>Span:</strong> ${escapeHtml(parts.join(' • '))}`;
          finding.appendChild(span);
        }

        findingsOutput.appendChild(finding);
      });
    }

    function renderCitations(items) {
      citationsOutput.innerHTML = '';
      if (!items.length) {
        citationsOutput.innerHTML = '<p class="empty">No citations returned.</p>';
        return;
      }

      items.forEach((item) => {
        const citation = document.createElement('article');
        citation.className = 'citation';
        const pageLabel = item.page ? `Page ${item.page}` : 'Location';
        citation.innerHTML = `<strong>${escapeHtml(pageLabel)}:</strong> ${escapeHtml(
          item.snippet || ''
        )}`;
        citationsOutput.appendChild(citation);
      });
    }

    async function handleFollowupRequest() {
      if (!followupInput) return;
      clearFollowupError();

      const question = followupInput.value.trim();
      if (!question) {
        showFollowupError('Enter a follow-up question.');
        followupInput.focus();
        return;
      }

      if (!latestAnalysisData) {
        showFollowupError('Run an analysis before asking a follow-up question.');
        return;
      }

      const context = buildFollowupContext(latestAnalysisData);
      if (!context) {
        showFollowupError('Analysis context is unavailable. Please rerun the analysis.');
        return;
      }

      addChatMessage({ role: 'user', content: question });
      followupInput.value = '';
      followupInput.focus();

      setFollowupLoading(true);

      const payload = {
        question,
        context,
        instruction: buildInstructionContext(),
        document: clampText(latestDocumentSource || '', 8000),
        history: buildHistoryPayload(),
      };

      try {
        const response = await fetch('/api/followup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });

        if (!response.ok) {
          const errorPayload = await safeJson(response);
          const detail = errorPayload?.detail;
          throw new Error(detail || 'Unable to process the follow-up question.');
        }

        const data = await response.json();
        const answer = typeof data.answer === 'string' ? data.answer.trim() : '';

        if (!answer) {
          throw new Error('The AI did not return an answer.');
        }

        addChatMessage({ role: 'assistant', content: answer });
        pushHistoryMessage('user', question);
        pushHistoryMessage('assistant', answer);
        persistFollowupState();
      } catch (error) {
        console.error(error);
        addChatMessage({ role: 'error', content: 'Network error, please try again.' });
        persistFollowupState();
      } finally {
        setFollowupLoading(false);
      }
    }

    function buildHistoryPayload() {
      if (!followupHistory.length) {
        return [];
      }
      return followupHistory.map((message) => ({ role: message.role, content: message.content }));
    }

    function pushHistoryMessage(role, content) {
      const sanitized = sanitizeHistoryMessage({ role, content });
      if (!sanitized) return;
      followupHistory.push(sanitized);
      if (followupHistory.length > FOLLOWUP_TRANSCRIPT_LIMIT * 2) {
        followupHistory = followupHistory.slice(-FOLLOWUP_TRANSCRIPT_LIMIT * 2);
      }
    }

    function sanitizeHistoryMessage(message) {
      if (!message || typeof message.content !== 'string') {
        return null;
      }
      const content = message.content.trim();
      if (!content) return null;
      let role = typeof message.role === 'string' ? message.role.toLowerCase() : 'user';
      if (role !== 'assistant' && role !== 'user') {
        role = role === 'system' ? 'assistant' : 'user';
      }
      return { role, content };
    }

    function addChatMessage(message, options = {}) {
      const normalized = normalizeChatMessage(message);
      if (!normalized) return null;

      followupTranscript.push(normalized);

      if (followupTranscript.length > FOLLOWUP_TRANSCRIPT_LIMIT) {
        followupTranscript = followupTranscript.slice(-FOLLOWUP_TRANSCRIPT_LIMIT);
        renderFollowupTranscript();
      } else if (followupConversation) {
        const bubble = createChatBubble(normalized);
        if (bubble) {
          followupConversation.appendChild(bubble);
        }
      }

      scrollFollowupConversation();

      if (options.persist !== false) {
        persistFollowupState();
      }

      return normalized;
    }

    function normalizeChatMessage(message) {
      if (!message || typeof message.content !== 'string') return null;
      const content = message.content.trim();
      if (!content) return null;
      let role = typeof message.role === 'string' ? message.role.toLowerCase() : 'assistant';
      if (role !== 'user' && role !== 'assistant' && role !== 'error') {
        role = role === 'system' ? 'assistant' : 'user';
      }
      return { role, content };
    }

    function renderFollowupTranscript() {
      if (!followupConversation) return;
      followupConversation.innerHTML = '';
      followupTranscript.forEach((message) => {
        const bubble = createChatBubble(message);
        if (bubble) {
          followupConversation.appendChild(bubble);
        }
      });
      scrollFollowupConversation();
    }

    function createChatBubble(message) {
      if (!message) return null;
      const bubble = document.createElement('div');
      bubble.className = `chat-message ${message.role}`;

      const sender = document.createElement('div');
      sender.className = 'chat-sender';
      if (message.role === 'assistant') {
        sender.textContent = 'LAWAgent';
      } else if (message.role === 'user') {
        sender.textContent = 'You';
      } else {
        sender.textContent = 'System';
      }

      const content = document.createElement('div');
      content.className = 'chat-content';
      content.textContent = message.content;

      bubble.appendChild(sender);
      bubble.appendChild(content);

      return bubble;
    }

    function scrollFollowupConversation() {
      if (!followupConversation) return;
      followupConversation.scrollTop = followupConversation.scrollHeight;
    }

    function resetFollowupConversation() {
      followupTranscript = [];
      followupHistory = [];
      if (followupConversation) {
        followupConversation.innerHTML = '';
      }
      persistFollowupState();
    }

    function updateStatus(message) {
      if (statusEl) {
        statusEl.textContent = message;
      }
    }

    function setLoading(isLoading) {
      submitBtn.disabled = isLoading;
      submitBtn.classList.toggle('loading', isLoading);
      if (isLoading) {
        submitBtn.setAttribute('aria-busy', 'true');
      } else {
        submitBtn.removeAttribute('aria-busy');
      }
    }

    function setFollowupLoading(isLoading) {
      if (!followupBtn) return;
      followupBtn.disabled = isLoading;
      followupBtn.classList.toggle('loading', isLoading);
      if (isLoading) {
        followupBtn.setAttribute('aria-busy', 'true');
      } else {
        followupBtn.removeAttribute('aria-busy');
      }
    }

    function showError(message) {
      if (!errorEl) return;
      errorEl.textContent = message;
      errorEl.hidden = false;
    }

    function clearError() {
      if (!errorEl) return;
      errorEl.textContent = '';
      errorEl.hidden = true;
    }

    function showFollowupError(message) {
      if (!followupError) return;
      followupError.textContent = message;
      followupError.hidden = false;
    }

    function clearFollowupError() {
      if (!followupError) return;
      followupError.textContent = '';
      followupError.hidden = true;
    }

    function buildFollowupContext(result) {
      if (!result) return '';
      const sections = [];

      if (result.summary) {
        sections.push(`Summary:\n${result.summary}`);
      }

      if (Array.isArray(result.findings) && result.findings.length) {
        const findingsText = result.findings
          .map((item, index) => {
            const parts = [];
            const heading = item.issue || `Finding ${index + 1}`;
            parts.push(`${index + 1}. ${heading}`);
            if (item.risk) {
              parts.push(`Risk: ${item.risk}`);
            }
            if (item.suggestion) {
              parts.push(`Suggestion: ${item.suggestion}`);
            }
            if (item.span && (item.span.page || item.span.start || item.span.end)) {
              const spanParts = [];
              if (item.span.page) spanParts.push(`Page ${item.span.page}`);
              if (item.span.start || item.span.end) {
                const start = item.span.start ?? '?';
                const end = item.span.end ?? '?';
                spanParts.push(`Chars ${start}-${end}`);
              }
              parts.push(`Span: ${spanParts.join(' • ')}`);
            }
            return parts.join('\n');
          })
          .join('\n\n');
        sections.push(`Findings:\n${findingsText}`);
      }

      if (Array.isArray(result.citations) && result.citations.length) {
        const citationsText = result.citations
          .map((item, index) => {
            const label = item.page ? `Page ${item.page}` : `Citation ${index + 1}`;
            const snippet = item.snippet || '';
            return `${label}: ${snippet}`.trim();
          })
          .join('\n');
        if (citationsText) {
          sections.push(`Citations:\n${citationsText}`);
        }
      }

      if (result.raw_json) {
        try {
          const raw =
            typeof result.raw_json === 'string'
              ? result.raw_json
              : JSON.stringify(result.raw_json, null, 2);
          if (raw) {
            sections.push(`Raw JSON:\n${raw}`);
          }
        } catch (error) {
          console.error('Failed to serialize raw analysis JSON', error);
        }
      }

      const context = sections.join('\n\n').trim();
      return clampText(context, 10000);
    }

    function buildInstructionContext() {
      const segments = [];
      if (latestInstructionText) {
        segments.push(latestInstructionText);
      }
      if (latestStyleSelection) {
        segments.push(`Preferred analysis style: ${latestStyleSelection}`);
      }
      return clampText(segments.join('\n\n'), 4000);
    }

    function persistFollowupState() {
      if (!sessionSupported) return;
      const state = {
        transcript: followupTranscript,
        history: followupHistory,
        latestAnalysis: latestAnalysisData,
        instruction: latestInstructionText,
        style: latestStyleSelection,
        document: latestDocumentSource,
      };
      try {
        sessionStorage.setItem(FOLLOWUP_STATE_KEY, JSON.stringify(state));
      } catch (error) {
        console.warn('Failed to persist follow-up state', error);
      }
    }

    function restoreFollowupState() {
      if (!sessionSupported) return;
      let stored;
      try {
        const raw = sessionStorage.getItem(FOLLOWUP_STATE_KEY);
        if (!raw) return;
        stored = JSON.parse(raw);
      } catch (error) {
        console.warn('Failed to restore follow-up state', error);
        return;
      }

      if (stored.latestAnalysis && typeof stored.latestAnalysis === 'object') {
        latestAnalysisData = stored.latestAnalysis;
      }
      if (typeof stored.instruction === 'string') {
        latestInstructionText = stored.instruction;
      }
      if (typeof stored.style === 'string') {
        latestStyleSelection = stored.style;
      }
      if (typeof stored.document === 'string') {
        latestDocumentSource = stored.document;
      }

      followupHistory = Array.isArray(stored.history)
        ? stored.history.map(sanitizeHistoryMessage).filter(Boolean)
        : [];
      followupTranscript = Array.isArray(stored.transcript)
        ? stored.transcript.map(normalizeChatMessage).filter(Boolean)
        : [];

      renderFollowupTranscript();
    }

    function clampText(value, maxLength) {
      const text = typeof value === 'string' ? value.trim() : '';
      if (!maxLength || text.length <= maxLength) {
        return text;
      }
      return `${text.slice(0, maxLength - 1)}…`;
    }

    function describeUploadedFile(file) {
      if (!file) return 'Uploaded file';
      const parts = [`Uploaded file: ${file.name || 'document'}`];
      if (file.type) {
        parts.push(`Type: ${file.type}`);
      }
      if (file.size) {
        const kb = Math.round(file.size / 1024);
        parts.push(`Size: ${kb}KB`);
      }
      return parts.join(' · ');
    }

    function supportsSessionStorage() {
      try {
        const key = '__lawagent_ss__';
        window.sessionStorage.setItem(key, '1');
        window.sessionStorage.removeItem(key);
        return true;
      } catch (error) {
        return false;
      }
    }

    function restoreThemePreference() {
      observeThemeChanges();
      if (!sessionSupported) return;
      try {
        const storedTheme = sessionStorage.getItem(THEME_STATE_KEY);
        if (storedTheme) {
          applyTheme(storedTheme);
        }
      } catch (error) {
        console.warn('Failed to restore theme preference', error);
      }
      persistThemePreference();
    }

    function observeThemeChanges() {
      const persist = () => {
        persistThemePreference();
      };

      const observer = new MutationObserver(persist);
      const targets = [document.documentElement, document.body];
      targets.forEach((target) => {
        if (!target) return;
        observer.observe(target, { attributes: true, attributeFilter: ['data-theme', 'class'] });
      });

      document.addEventListener('lawagent:theme-change', persist);
    }

    function persistThemePreference() {
      if (!sessionSupported) return;
      const theme = detectTheme();
      if (!theme) return;
      try {
        sessionStorage.setItem(THEME_STATE_KEY, theme);
      } catch (error) {
        console.warn('Failed to persist theme preference', error);
      }
    }

    function detectTheme() {
      const html = document.documentElement;
      const body = document.body;
      const attr =
        (html && (html.dataset.theme || html.getAttribute('data-theme'))) ||
        (body && (body.dataset.theme || body.getAttribute('data-theme')));
      if (attr) {
        return attr.toLowerCase();
      }

      const classes = [
        ...(html ? Array.from(html.classList || []) : []),
        ...(body ? Array.from(body.classList || []) : []),
      ];

      if (classes.some((name) => /light/i.test(name))) {
        return 'light';
      }
      if (classes.some((name) => /dark/i.test(name))) {
        return 'dark';
      }
      return '';
    }

    function applyTheme(theme) {
      if (!theme) return;
      const normalized = theme.toLowerCase();
      if (document.documentElement) {
        document.documentElement.setAttribute('data-theme', normalized);
        document.documentElement.dataset.theme = normalized;
      }
      if (document.body) {
        document.body.setAttribute('data-theme', normalized);
        document.body.dataset.theme = normalized;
      }
    }
    }

    async function safeJson(response) {
      try {
        return await response.json();
      } catch (error) {
        return null;
      }
    }

    function escapeHtml(value) {
      return (value || '')
        .toString()
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }
  });
})();
