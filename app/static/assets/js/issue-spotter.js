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

    const tabGroupId = 'results';

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      clearError();

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
