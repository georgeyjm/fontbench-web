// Cookie utilities
function setCookie(name, value, days = 365) {
    const expires = new Date(Date.now() + days * 864e5).toUTCString();
    document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/`;
}

function getCookie(name) {
    const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : null;
}

// State
const state = {
    availableTypefaces: [],  // Array of { id, name }
    addedTypefaces: [], // { id, name, fonts: [{ id, name, masters: [], enabledMasters: Set }], enabled: bool, color: {h, s, l} }
    fontData: new Map(), // fontId -> { masters: [], data: Map<master, {chars, values}> }
    chartType: 'scatter', // 'scatter', 'histogram', 'rank'
    binSize: 0.01,
    currentCharset: '3500',
    referenceTrace: null, // { typefaceId, fontId, fontName, master } - used for scatter plot sorting
    useWebGL: true, // Use WebGL (scattergl) for faster rendering
};

// Color palette - different hues for different fonts
const FONT_HUES = [210, 0, 120, 45, 280, 180, 330, 90];
let hueIndex = 0;

// DOM Elements
const elements = {
    fontList: document.getElementById('fontList'),
    addFontBtn: document.getElementById('addFontBtn'),
    fontModal: document.getElementById('fontModal'),
    fontModalList: document.getElementById('fontModalList'),
    modalClose: document.getElementById('modalClose'),
    charsetSelect: document.getElementById('charsetSelect'),
    chartContainer: document.getElementById('chartContainer'),
    emptyState: document.getElementById('emptyState'),
    chartSubtitle: document.getElementById('chartSubtitle'),
    binControl: document.getElementById('binControl'),
    binSizeInput: document.getElementById('binSize'),
    settingsBtn: document.getElementById('settingsBtn'),
    settingsModal: document.getElementById('settingsModal'),
    settingsClose: document.getElementById('settingsClose'),
    webglToggle: document.getElementById('webglToggle'),
};

// Icons
const icons = {
    plus: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="12" y1="5" x2="12" y2="19"/>
        <line x1="5" y1="12" x2="19" y2="12"/>
    </svg>`,
    spinner: `<span class="spinner"></span>`,
    remove: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="18" y1="6" x2="6" y2="18"/>
        <line x1="6" y1="6" x2="18" y2="18"/>
    </svg>`,
};

// API functions
async function fetchAvailableTypefaces(metric = 'grayscale') {
    const response = await fetch(`/api/data/${metric}`);
    const data = await response.json();
    return data.typefaces;  // Array of { id, name }
}

async function fetchTypefaceFonts(typefaceId, charset, metric = 'grayscale') {
    // Fetch typeface info with all fonts and their masters
    const response = await fetch(`/api/data/${metric}/${typefaceId}?charset=${charset}`);
    const data = await response.json();
    return data;  // { typeface_id, typeface_name, fonts: [{ id, name, masters }] }
}

async function fetchFontMasterData(typefaceId, fontId, master, charset, metric = 'grayscale') {
    const response = await fetch(
        `/api/data/${metric}/${typefaceId}/${fontId}?charset=${charset}&master=${encodeURIComponent(master)}`
    );
    const data = await response.json();
    return {
        chars: data.chart_data.text,
        values: data.chart_data.y,
    };
}

async function fetchAllFontData(typefaceId, fonts, charset, metric = 'grayscale') {
    // Fetch data for all fonts and masters in parallel
    const allPromises = [];

    for (const font of fonts) {
        for (const master of font.masters) {
            allPromises.push(
                fetchFontMasterData(typefaceId, font.id, master, charset, metric)
                    .then(data => ({ fontId: font.id, master, ...data }))
            );
        }
    }

    const results = await Promise.all(allPromises);

    // Organize by fontId
    const fontDataMap = new Map();
    for (const result of results) {
        if (!fontDataMap.has(result.fontId)) {
            fontDataMap.set(result.fontId, { data: new Map() });
        }
        fontDataMap.get(result.fontId).data.set(result.master, {
            chars: result.chars,
            values: result.values,
        });
    }

    return fontDataMap;
}

// Color utilities
function getNextFontColor() {
    const h = FONT_HUES[hueIndex % FONT_HUES.length];
    hueIndex++;
    return { h, s: 60, l: 50 };
}

function getMasterColor(baseColor, index, total) {
    const minL = 35;
    const maxL = 65;
    const l = total === 1 ? 50 : minL + (maxL - minL) * (index / (total - 1));
    return `hsl(${baseColor.h}, ${baseColor.s}%, ${l}%)`;
}

// UI functions
function renderFontList() {
    const typefacesHtml = state.addedTypefaces.map((typeface, typefaceIndex) => {
        // Count total masters across all fonts for color distribution
        const totalMasters = typeface.fonts.reduce((sum, f) => sum + f.masters.length, 0);
        let masterColorIndex = 0;

        const fontsHtml = typeface.fonts.map((font) => {
            const mastersHtml = font.masters.map((master) => {
                const color = getMasterColor(typeface.color, masterColorIndex, totalMasters);
                masterColorIndex++;
                const checked = font.enabledMasters.has(master) ? 'checked' : '';
                const traceName = totalMasters > 1 ? `${typeface.name} - ${master}` : typeface.name;
                const isReference = state.referenceTrace?.fontId === font.id && state.referenceTrace?.master === master;
                const refClass = isReference ? 'reference-btn active' : 'reference-btn';
                return `
                    <div class="master-item" data-trace="${traceName}" data-typeface-id="${typeface.id}" data-font-id="${font.id}" data-master-name="${master}">
                        <input type="checkbox" class="master-checkbox"
                            data-typeface="${typefaceIndex}" data-font-id="${font.id}" data-master="${master}" ${checked}>
                        <span class="master-name">${master}</span>
                        <span class="master-color" style="background: ${color}"></span>
                        <button class="${refClass}" data-typeface-id="${typeface.id}" data-font-id="${font.id}" data-master-name="${master}" title="设为排序参考">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                                <circle cx="12" cy="10" r="4"/>
                                <path d="M12 14v6"/>
                            </svg>
                        </button>
                    </div>
                `;
            }).join('');
            return mastersHtml;
        }).join('');

        const allChecked = typeface.enabled ? 'checked' : '';

        return `
            <div class="font-item" data-typeface-id="${typeface.id}">
                <div class="font-header">
                    <input type="checkbox" class="font-checkbox" data-typeface="${typefaceIndex}" ${allChecked}>
                    <span class="font-name">${typeface.name}</span>

                    <button class="font-remove" data-typeface="${typefaceIndex}">${icons.remove}</button>
                </div>
                <div class="master-list">${fontsHtml}</div>
            </div>
        `;
    }).join('');

    // Add the button at the end
    const addBtnHtml = `
        <button class="add-font-btn" id="addFontBtn">
            ${icons.plus}
            添加字体
        </button>
    `;

    elements.fontList.innerHTML = typefacesHtml + addBtnHtml;

    // Re-acquire addFontBtn reference and attach listener
    elements.addFontBtn = document.getElementById('addFontBtn');
    elements.addFontBtn.addEventListener('click', openFontModal);

    // Attach event listeners
    elements.fontList.querySelectorAll('.font-checkbox').forEach(cb => {
        cb.addEventListener('change', handleTypefaceToggle);
    });
    elements.fontList.querySelectorAll('.master-checkbox').forEach(cb => {
        cb.addEventListener('change', handleMasterToggle);
    });
    elements.fontList.querySelectorAll('.font-remove').forEach(btn => {
        btn.addEventListener('click', handleTypefaceRemove);
    });

    // Hover highlight listeners for individual masters
    elements.fontList.querySelectorAll('.master-item').forEach(item => {
        item.addEventListener('mouseenter', () => highlightTrace(item.dataset.trace));
        item.addEventListener('mouseleave', () => highlightTrace(null));
    });

    // Hover highlight listeners for entire typeface (highlights all masters)
    elements.fontList.querySelectorAll('.font-header').forEach(header => {
        const fontItem = header.closest('.font-item');
        const typefaceId = fontItem?.dataset.typefaceId;
        if (typefaceId) {
            const typeface = state.addedTypefaces.find(t => t.id === parseInt(typefaceId));
            if (typeface) {
                header.addEventListener('mouseenter', () => highlightTypeface(typeface.name));
                header.addEventListener('mouseleave', () => highlightTrace(null));
            }
        }
    });

    // Reference button click listeners
    elements.fontList.querySelectorAll('.reference-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const typefaceId = parseInt(btn.dataset.typefaceId);
            const fontId = parseInt(btn.dataset.fontId);
            const masterName = btn.dataset.masterName;
            setReference(typefaceId, fontId, masterName);
        });
    });
}

function updateChart() {
    const traces = [];
    const isScatter = state.chartType === 'scatter';
    const isRank = state.chartType === 'rank';
    const isHistogram = state.chartType === 'histogram';

    // For scatter mode, get reference character order
    let referenceCharOrder = null;
    if (isScatter) {
        const ref = state.referenceTrace || getFirstEnabledMaster();
        if (ref) {
            const refFontData = state.fontData.get(ref.fontId);
            const refMasterData = refFontData?.data.get(ref.master);
            if (refMasterData) {
                // Create a map of character -> index based on reference order
                referenceCharOrder = new Map();
                refMasterData.chars.forEach((char, idx) => {
                    referenceCharOrder.set(char, idx);
                });
            }
        }
    }

    state.addedTypefaces.forEach((typeface) => {
        // Count total masters for color distribution
        const totalMasters = typeface.fonts.reduce((sum, f) => sum + f.masters.length, 0);
        let masterColorIndex = 0;

        typeface.fonts.forEach((font) => {
            const fontData = state.fontData.get(font.id);
            if (!fontData) return;

            font.masters.forEach((master) => {
                const masterData = fontData.data.get(master);
                if (!masterData) {
                    masterColorIndex++;
                    return;
                }
                if (!font.enabledMasters.has(master)) {
                    masterColorIndex++;
                    return;
                }

                const color = getMasterColor(typeface.color, masterColorIndex, totalMasters);
                masterColorIndex++;
                const traceName = totalMasters > 1 ? `${typeface.name} - ${master}` : typeface.name;

            if (isScatter) {
                // Reorder data according to reference character order
                let xData, yData, textData;
                if (referenceCharOrder) {
                    // Create array of {char, value, refIndex}
                    const combined = masterData.chars.map((char, i) => ({
                        char,
                        value: masterData.values[i],
                        refIndex: referenceCharOrder.get(char) ?? Infinity,
                    }));
                    // Sort by reference index
                    combined.sort((a, b) => a.refIndex - b.refIndex);
                    // Filter out characters not in reference
                    const filtered = combined.filter(d => d.refIndex !== Infinity);
                    xData = filtered.map(d => d.char);
                    yData = filtered.map(d => d.value);
                    textData = xData;
                } else {
                    xData = masterData.chars;
                    yData = masterData.values;
                    textData = xData;
                }

                const scatterType = state.useWebGL ? 'scattergl' : 'scatter';
                traces.push({
                    x: textData,
                    y: yData,
                    type: scatterType,
                    mode: 'markers',
                    name: traceName,
                    marker: { size: 4, color },
                    hovertemplate: '<b>%{x}</b><br>灰度: %{y:.4f}<extra></extra>',
                });
            } else if (isRank) {
                // Rank mode: x-axis is percentile (0-100%)
                const n = masterData.values.length;
                const xData = masterData.values.map((_, i) => (i / (n - 1)) * 100);

                const scatterType = state.useWebGL ? 'scattergl' : 'scatter';
                traces.push({
                    x: xData,
                    y: masterData.values,
                    text: masterData.chars,
                    type: scatterType,
                    mode: 'markers',
                    name: traceName,
                    marker: { size: 4, color },
                    hovertemplate: '<b>%{text}</b><br>百分位: %{x:.1f}%<br>灰度: %{y:.4f}<extra></extra>',
                });
            } else {
                // Histogram
                traces.push({
                    x: masterData.values,
                    type: 'histogram',
                    name: traceName,
                    marker: { color },
                    opacity: 0.7,
                    xbins: { size: state.binSize },
                    hovertemplate: '灰度: %{x:.4f}<br>数量: %{y}<extra></extra>',
                });
            }
            });
        });
    });

    if (traces.length === 0) {
        elements.emptyState.style.display = 'flex';
        elements.chartSubtitle.textContent = '';
        Plotly.purge('chartContainer');
        return;
    }

    elements.emptyState.style.display = 'none';
    if (isHistogram) {
        elements.chartSubtitle.textContent = `${traces.length} 个分布`;
    } else if (isRank) {
        elements.chartSubtitle.textContent = `${traces.length} 条曲线 (百分位排序)`;
    } else {
        const ref = state.referenceTrace || getFirstEnabledMaster();
        const refName = ref ? (ref.typefaceName + (ref.master ? ` - ${ref.master}` : '')) : '';
        elements.chartSubtitle.textContent = `${traces.length} 条曲线` + (refName ? ` (参考: ${refName})` : '');
    }

    const layout = {
        margin: { t: 20, r: 30, b: 30, l: 60 },
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        font: {
            family: '-apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif',
            size: 12,
            color: '#666',
        },
        xaxis: {
            showgrid: isHistogram || isRank,
            gridcolor: '#f5f5f5',
            showline: true,
            linecolor: '#eee',
            tickfont: { size: 12 },
            tickangle: 0,
            nticks: isHistogram ? 20 : (isRank ? 10 : 50),
            title: isRank ? { text: '百分位 (%)', font: { size: 11, color: '#999' } } : undefined,
        },
        yaxis: {
            title: {
                text: isHistogram ? '字符数量' : '灰度值',
                font: { size: 11, color: '#999' },
                standoff: 10,
            },
            showgrid: true,
            gridcolor: '#f5f5f5',
            showline: true,
            linecolor: '#eee',
            zeroline: false,
        },
        hovermode: 'closest',
        hoverlabel: {
            bgcolor: '#1a1a1a',
            bordercolor: '#1a1a1a',
            font: {
                family: '-apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif',
                size: 13,
                color: 'white',
            },
        },
        showlegend: false,
        barmode: isHistogram ? 'overlay' : undefined,
    };

    const config = {
        responsive: true,
        displayModeBar: true,
        displaylogo: false,
        modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
    };

    Plotly.newPlot('chartContainer', traces, layout, config);
}

function highlightTrace(traceName) {
    const chartDiv = document.getElementById('chartContainer');
    if (!chartDiv || !chartDiv.data) return;

    const traceCount = chartDiv.data.length;
    if (traceCount === 0) return;

    const defaultOpacity = state.chartType === 'histogram' ? 0.7 : 1;

    if (traceName === null) {
        // Reset all traces to full opacity
        const opacities = chartDiv.data.map(() => defaultOpacity);
        Plotly.restyle('chartContainer', { opacity: opacities });
    } else {
        // Dim all except the hovered trace
        const opacities = chartDiv.data.map(trace =>
            trace.name === traceName ? 1 : 0.25
        );
        Plotly.restyle('chartContainer', { opacity: opacities });
    }
}

function highlightTypeface(typefaceName) {
    const chartDiv = document.getElementById('chartContainer');
    if (!chartDiv || !chartDiv.data) return;

    const traceCount = chartDiv.data.length;
    if (traceCount === 0) return;

    // Highlight all traces that belong to this typeface
    const opacities = chartDiv.data.map(trace =>
        trace.name === typefaceName || trace.name.startsWith(`${typefaceName} - `) ? 1 : 0.1
    );
    Plotly.restyle('chartContainer', { opacity: opacities });
}

function setReference(typefaceId, fontId, masterName) {
    // Toggle reference off if clicking the same one
    if (state.referenceTrace?.fontId === fontId && state.referenceTrace?.master === masterName) {
        state.referenceTrace = null;
    } else {
        const typeface = state.addedTypefaces.find(t => t.id === typefaceId);
        state.referenceTrace = { typefaceId, fontId, typefaceName: typeface?.name, master: masterName };
    }
    renderFontList();
    updateChart();
}

function getFirstEnabledMaster() {
    for (const typeface of state.addedTypefaces) {
        for (const font of typeface.fonts) {
            for (const master of font.masters) {
                if (font.enabledMasters.has(master)) {
                    return { typefaceId: typeface.id, fontId: font.id, typefaceName: typeface.name, master };
                }
            }
        }
    }
    return null;
}

// Event handlers
async function handleAddTypeface(typefaceId, typefaceName, modalItem) {
    if (state.addedTypefaces.some(t => t.id === typefaceId)) {
        return;
    }

    // Mark modal item as loading
    modalItem.classList.add('loading');
    modalItem.innerHTML = `${icons.spinner} ${typefaceName}`;

    try {
        const charset = elements.charsetSelect.value;
        const typefaceData = await fetchTypefaceFonts(typefaceId, charset);

        // Prepare fonts with enabledMasters
        const fonts = typefaceData.fonts.map(f => ({
            id: f.id,
            name: f.name,
            masters: f.masters,
            enabledMasters: new Set(f.masters),
        }));

        // Fetch all font data
        const fontDataMap = await fetchAllFontData(typefaceId, fonts, charset);

        // Store font data
        for (const [fontId, data] of fontDataMap) {
            state.fontData.set(fontId, data);
        }

        state.addedTypefaces.push({
            id: typefaceId,
            name: typefaceName,
            fonts: fonts,
            enabled: true,
            color: getNextFontColor(),
        });

        renderFontList();
        updateChart();

        // Mark as added (keep disabled)
        modalItem.innerHTML = `✓ ${typefaceName}`;
        modalItem.classList.remove('loading');
        modalItem.classList.add('added');
    } catch (error) {
        console.error('Failed to load typeface:', error);
        // Restore item on error
        modalItem.classList.remove('loading');
        modalItem.textContent = typefaceName;
    }
}

function handleTypefaceToggle(e) {
    const typefaceIndex = parseInt(e.target.dataset.typeface);
    const typeface = state.addedTypefaces[typefaceIndex];
    typeface.enabled = e.target.checked;

    // Toggle all masters in all fonts
    for (const font of typeface.fonts) {
        if (typeface.enabled) {
            font.enabledMasters = new Set(font.masters);
        } else {
            font.enabledMasters.clear();
        }
    }

    renderFontList();
    updateChart();
}

function handleMasterToggle(e) {
    const typefaceIndex = parseInt(e.target.dataset.typeface);
    const fontId = parseInt(e.target.dataset.fontId);
    const masterName = e.target.dataset.master;
    const typeface = state.addedTypefaces[typefaceIndex];
    const font = typeface.fonts.find(f => f.id === fontId);

    if (!font) return;

    if (e.target.checked) {
        font.enabledMasters.add(masterName);
    } else {
        font.enabledMasters.delete(masterName);
    }

    // Update typeface enabled state based on all fonts/masters
    const allMastersEnabled = typeface.fonts.every(f =>
        f.masters.every(m => f.enabledMasters.has(m))
    );
    typeface.enabled = allMastersEnabled;

    renderFontList();
    updateChart();
}

function handleTypefaceRemove(e) {
    const typefaceIndex = parseInt(e.currentTarget.dataset.typeface);
    const typeface = state.addedTypefaces[typefaceIndex];

    // Remove all font data for this typeface
    for (const font of typeface.fonts) {
        state.fontData.delete(font.id);
    }

    state.addedTypefaces.splice(typefaceIndex, 1);
    renderFontList();
    updateChart();
}

function openFontModal() {
    const addedIds = new Set(state.addedTypefaces.map(t => t.id));

    if (state.availableTypefaces.length === 0) {
        elements.fontModalList.innerHTML = '<div class="no-fonts">没有可用字体</div>';
    } else {
        elements.fontModalList.innerHTML = state.availableTypefaces.map(typeface => {
            const isAdded = addedIds.has(typeface.id);
            const className = isAdded ? 'modal-item added' : 'modal-item';
            const content = isAdded ? `✓ ${typeface.name}` : typeface.name;
            return `<div class="${className}" data-typeface-id="${typeface.id}" data-typeface-name="${typeface.name}">${content}</div>`;
        }).join('');

        elements.fontModalList.querySelectorAll('.modal-item:not(.added)').forEach(item => {
            const typefaceId = parseInt(item.dataset.typefaceId);
            const typefaceName = item.dataset.typefaceName;
            item.addEventListener('click', () => handleAddTypeface(typefaceId, typefaceName, item));
        });
    }

    elements.fontModal.classList.add('active');
}

async function handleCharsetChange() {
    const newCharset = elements.charsetSelect.value;
    if (newCharset === state.currentCharset) return;

    state.currentCharset = newCharset;

    if (state.addedTypefaces.length === 0) return;

    try {
        // Reload data for all typefaces with new charset
        for (const typeface of state.addedTypefaces) {
            const typefaceData = await fetchTypefaceFonts(typeface.id, newCharset);

            // Update fonts with new masters
            for (const fontData of typefaceData.fonts) {
                const font = typeface.fonts.find(f => f.id === fontData.id);
                if (font) {
                    font.masters = fontData.masters;
                    // Keep only masters that still exist
                    font.enabledMasters = new Set(
                        [...font.enabledMasters].filter(m => fontData.masters.includes(m))
                    );
                    // If no masters enabled, enable all
                    if (font.enabledMasters.size === 0) {
                        font.enabledMasters = new Set(fontData.masters);
                    }
                }
            }

            // Refetch all font data
            const fontDataMap = await fetchAllFontData(typeface.id, typeface.fonts, newCharset);
            for (const [fontId, data] of fontDataMap) {
                state.fontData.set(fontId, data);
            }

            // Update typeface enabled state
            const allMastersEnabled = typeface.fonts.every(f =>
                f.masters.every(m => f.enabledMasters.has(m))
            );
            typeface.enabled = allMastersEnabled;
        }

        renderFontList();
        updateChart();
    } catch (error) {
        console.error('Failed to reload fonts:', error);
    }
}

function handleChartTypeChange(e) {
    const btn = e.currentTarget;
    const type = btn.dataset.type;
    if (type === state.chartType) return;

    state.chartType = type;

    document.querySelectorAll('.chart-type-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.type === type);
    });

    elements.binControl.classList.toggle('active', type === 'histogram');
    updateChart();
}

function handleBinSizeChange(e) {
    const value = parseFloat(e.target.value);
    if (value > 0 && value <= 0.1) {
        state.binSize = value;
        updateChart();
    }
}

// Initialize
async function init() {
    // Load settings from cookies
    const webglCookie = getCookie('useWebGL');
    if (webglCookie !== null) {
        state.useWebGL = webglCookie === 'true';
        elements.webglToggle.checked = state.useWebGL;
    }

    // Set initial charset from select
    state.currentCharset = elements.charsetSelect.value;

    try {
        state.availableTypefaces = await fetchAvailableTypefaces();
    } catch (error) {
        console.error('Failed to load available typefaces:', error);
    }

    // Event listeners
    elements.addFontBtn.addEventListener('click', openFontModal);
    elements.modalClose.addEventListener('click', () => elements.fontModal.classList.remove('active'));
    elements.fontModal.addEventListener('click', (e) => {
        if (e.target === elements.fontModal) elements.fontModal.classList.remove('active');
    });
    elements.charsetSelect.addEventListener('change', handleCharsetChange);
    elements.binSizeInput.addEventListener('change', handleBinSizeChange);

    // Settings modal
    elements.settingsBtn.addEventListener('click', () => elements.settingsModal.classList.add('active'));
    elements.settingsClose.addEventListener('click', () => elements.settingsModal.classList.remove('active'));
    elements.settingsModal.addEventListener('click', (e) => {
        if (e.target === elements.settingsModal) elements.settingsModal.classList.remove('active');
    });
    elements.webglToggle.addEventListener('change', (e) => {
        state.useWebGL = e.target.checked;
        setCookie('useWebGL', state.useWebGL);
        updateChart();
    });

    document.querySelectorAll('.chart-type-btn').forEach(btn => {
        btn.addEventListener('click', handleChartTypeChange);
    });
}

init();
