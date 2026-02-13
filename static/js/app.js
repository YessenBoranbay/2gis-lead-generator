/**
 * 2GIS Lead Generator - Frontend
 */

let statusCheckInterval = null;

const searchForm = document.getElementById('searchForm');
const searchBtn = document.getElementById('searchBtn');
const resetBtn = document.getElementById('resetBtn');
const downloadBtn = document.getElementById('downloadBtn');
const statusPanel = document.getElementById('statusPanel');
const resultsPanel = document.getElementById('resultsPanel');
const errorPanel = document.getElementById('errorPanel');
const statusMessage = document.getElementById('statusMessage');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const resultsBody = document.getElementById('resultsBody');
const resultsCount = document.getElementById('resultsCount');
const errorMessage = document.getElementById('errorMessage');

function showError(msg) {
    errorMessage.textContent = msg;
    errorPanel.hidden = false;
}

function hideError() {
    errorPanel.hidden = true;
}

function setSearching(active) {
    searchBtn.disabled = active;
    searchBtn.innerHTML = active
        ? '<span class="loading"></span>Поиск...'
        : 'Найти компании';
}

function updateStatus(status) {
    statusMessage.textContent = status.current || 'Обработка...';
    if (status.total > 0) {
        const pct = Math.min((status.progress / status.total) * 100, 100);
        progressFill.style.width = pct + '%';
        progressText.textContent = `${status.progress} / ${status.total}`;
    } else {
        progressFill.style.width = status.progress > 0 ? '30%' : '5%';
        progressText.textContent = status.progress > 0 ? `${status.progress}...` : 'Инициализация...';
    }
}

function showResults(results) {
    resultsCount.textContent = `${results.length} компаний`;
    resultsBody.innerHTML = '';
    results.forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${escapeHtml(r['Название компании'] || '—')}</strong></td>
            <td>${escapeHtml(r['Город'] !== 'N/A' ? r['Город'] : '—')}</td>
            <td>${escapeHtml(r['Телефон'] !== 'N/A' ? r['Телефон'] : '—')}</td>
            <td>${escapeHtml(r['Адрес'] !== 'N/A' ? r['Адрес'] : '—')}</td>
            <td>${r['Рейтинг'] !== 'N/A' ? r['Рейтинг'] : '—'}</td>
            <td>${r['Количество голосов'] !== 'N/A' ? r['Количество голосов'] : '—'}</td>
        `;
        resultsBody.appendChild(tr);
    });
    resultsPanel.hidden = false;
    resetBtn.style.display = 'inline-block';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function autoDownloadExcel() {
    try {
        const res = await fetch('/api/download', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
        if (!res.ok) return;
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = '2gis_results.xlsx';
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        console.warn('Auto-download failed', e);
    }
}

async function safeJson(res) {
    const ct = res.headers.get('content-type') || '';
    if (!ct.includes('application/json')) {
        throw new Error('Сервер вернул неверный ответ. Попробуйте обновить страницу.');
    }
    return res.json();
}

function startStatusCheck() {
    if (statusCheckInterval) clearInterval(statusCheckInterval);
    statusCheckInterval = setInterval(async () => {
        try {
            const res = await fetch('/api/status');
            const status = await safeJson(res);
            updateStatus(status);
            if (!status.is_running) {
                clearInterval(statusCheckInterval);
                statusCheckInterval = null;
                setSearching(false);
                if (status.error) showError(status.error);
                else if (status.results?.length) {
                    showResults(status.results);
                    setTimeout(autoDownloadExcel, 800);
                }
            }
        } catch (e) {
            clearInterval(statusCheckInterval);
            statusCheckInterval = null;
            setSearching(false);
        }
    }, 1000);
}

searchForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const country = document.getElementById('country').value.trim();
    const city = document.getElementById('city').value.trim();
    const category = document.getElementById('category').value.trim();
    const maxResults = document.getElementById('maxResults').value;

    if (!city) {
        showError('Выберите город или "Вся страна"');
        return;
    }

    resultsPanel.hidden = true;
    hideError();
    statusPanel.hidden = false;
    setSearching(true);

    try {
        const res = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                country: country || null,
                city: city === '__WHOLE_COUNTRY__' ? null : (city || null),
                category: category || null,
                max_results: maxResults ? parseInt(maxResults, 10) : null,
                whole_country: city === '__WHOLE_COUNTRY__'
            })
        });
        const data = await safeJson(res);
        if (!res.ok) throw new Error(data.error || 'Ошибка запуска');
        startStatusCheck();
    } catch (err) {
        showError(err.message);
        setSearching(false);
        statusPanel.hidden = true;
    }
});

resetBtn.addEventListener('click', async () => {
    try {
        await fetch('/api/reset', { method: 'POST' });
    } catch (e) {}
    statusPanel.hidden = true;
    resultsPanel.hidden = true;
    errorPanel.hidden = true;
    resetBtn.style.display = 'none';
    document.getElementById('country').value = 'Россия';
    if (window.updateCities) window.updateCities();
    document.getElementById('city').value = '';
    document.getElementById('category').value = '';
    document.getElementById('maxResults').value = '';
    resultsBody.innerHTML = '';
});

downloadBtn.addEventListener('click', async () => {
    try {
        const res = await fetch('/api/download', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
        if (!res.ok) {
            const data = await safeJson(res).catch(() => ({}));
            throw new Error(data.error || 'Ошибка');
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = '2gis_results.xlsx';
        a.click();
        URL.revokeObjectURL(url);
    } catch (err) {
        showError('Ошибка скачивания: ' + err.message);
    }
});
