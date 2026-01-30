// State
const state = {
    availableFonts: [],
    addedFonts: [], // { name, masters: [], enabledMasters: Set, enabled: bool, color: {h, s, l} }
    fontData: new Map(), // fontName -> { masters: [], data: Map<master, {chars, values}> }
    chartType: 'scatter', // 'scatter', 'histogram', 'rank'
    binSize: 0.01,
    currentCharset: '3500',
    referenceTrace: null, // { fontName, master } - used for scatter plot sorting
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
async function fetchAvailableFonts(metric = 'grayscale') {
    const response = await fetch(`/api/data/${metric}`);
    const data = await response.json();
    return data.files;
}

async function fetchGrayscaleData(fontName, charset, metric = 'grayscale') {
    // Fetch initial data to get masters list
    const response = await fetch(`/api/data/${metric}/${encodeURIComponent(fontName)}?charset=${charset}`);
    const data = await response.json();

    const fontData = {
        masters: data.masters,
        data: new Map(),
    };

    // Fetch data for each master in parallel
    const masterPromises = data.masters.map(async (master) => {
        const masterResponse = await fetch(
            `/api/data/${metric}/${encodeURIComponent(fontName)}?charset=${charset}&master=${encodeURIComponent(master)}`
        );
        const masterData = await masterResponse.json();
        return {
            master,
            chars: masterData.chart_data.text,
            values: masterData.chart_data.y,
        };
    });

    const masterResults = await Promise.all(masterPromises);
    masterResults.forEach(({ master, chars, values }) => {
        fontData.data.set(master, { chars, values });
    });

    return fontData;
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
    const fontsHtml = state.addedFonts.map((font, fontIndex) => {
        const mastersHtml = font.masters.map((master, masterIndex) => {
            const color = getMasterColor(font.color, masterIndex, font.masters.length);
            const checked = font.enabledMasters.has(master) ? 'checked' : '';
            const traceName = font.masters.length > 1 ? `${font.name} - ${master}` : font.name;
            const isReference = state.referenceTrace?.fontName === font.name && state.referenceTrace?.master === master;
            const refClass = isReference ? 'reference-btn active' : 'reference-btn';
            return `
                <div class="master-item" data-trace="${traceName}" data-font-name="${font.name}" data-master-name="${master}">
                    <input type="checkbox" class="master-checkbox"
                        data-font="${fontIndex}" data-master="${master}" ${checked}>
                    <span class="master-name">${master}</span>
                    <span class="master-color" style="background: ${color}"></span>
                    <button class="${refClass}" data-font-name="${font.name}" data-master-name="${master}" title="设为排序参考">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                            <circle cx="12" cy="10" r="4"/>
                            <path d="M12 14v6"/>
                        </svg>
                    </button>
                </div>
            `;
        }).join('');

        const allChecked = font.enabled ? 'checked' : '';
        const baseColor = `hsl(${font.color.h}, ${font.color.s}%, ${font.color.l}%)`;

        return `
            <div class="font-item" data-font-name="${font.name}">
                <div class="font-header">
                    <input type="checkbox" class="font-checkbox" data-font="${fontIndex}" ${allChecked}>
                    <span class="font-name">${font.name}</span>
                    
                    <button class="font-remove" data-font="${fontIndex}">${icons.remove}</button>
                </div>
                <div class="master-list">${mastersHtml}</div>
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

    elements.fontList.innerHTML = fontsHtml + addBtnHtml;

    // Re-acquire addFontBtn reference and attach listener
    elements.addFontBtn = document.getElementById('addFontBtn');
    elements.addFontBtn.addEventListener('click', openFontModal);

    // Attach event listeners
    elements.fontList.querySelectorAll('.font-checkbox').forEach(cb => {
        cb.addEventListener('change', handleFontToggle);
    });
    elements.fontList.querySelectorAll('.master-checkbox').forEach(cb => {
        cb.addEventListener('change', handleMasterToggle);
    });
    elements.fontList.querySelectorAll('.font-remove').forEach(btn => {
        btn.addEventListener('click', handleFontRemove);
    });

    // Hover highlight listeners for individual masters
    elements.fontList.querySelectorAll('.master-item').forEach(item => {
        item.addEventListener('mouseenter', () => highlightTrace(item.dataset.trace));
        item.addEventListener('mouseleave', () => highlightTrace(null));
    });

    // Hover highlight listeners for entire font (highlights all masters)
    elements.fontList.querySelectorAll('.font-header').forEach(header => {
        const fontItem = header.closest('.font-item');
        const fontName = fontItem?.dataset.fontName;
        if (fontName) {
            header.addEventListener('mouseenter', () => highlightFont(fontName));
            header.addEventListener('mouseleave', () => highlightTrace(null));
        }
    });

    // Reference button click listeners
    elements.fontList.querySelectorAll('.reference-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const fontName = btn.dataset.fontName;
            const masterName = btn.dataset.masterName;
            setReference(fontName, masterName);
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
            const refFontData = state.fontData.get(ref.fontName);
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

    state.addedFonts.forEach((font) => {
        const fontData = state.fontData.get(font.name);
        if (!fontData) return;

        const enabledMasters = Array.from(font.enabledMasters);
        enabledMasters.forEach((master) => {
            const masterData = fontData.data.get(master);
            if (!masterData) return;

            const masterIndexInAll = font.masters.indexOf(master);
            const color = getMasterColor(font.color, masterIndexInAll, font.masters.length);
            const traceName = font.masters.length > 1 ? `${font.name} - ${master}` : font.name;

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

                traces.push({
                    x: textData,
                    y: yData,
                    type: 'scatter',
                    mode: 'markers',
                    name: traceName,
                    marker: { size: 4, color },
                    hovertemplate: '<b>%{x}</b><br>灰度: %{y:.4f}<extra></extra>',
                });
            } else if (isRank) {
                // Rank mode: x-axis is percentile (0-100%)
                const n = masterData.values.length;
                const xData = masterData.values.map((_, i) => (i / (n - 1)) * 100);

                traces.push({
                    x: xData,
                    y: masterData.values,
                    text: masterData.chars,
                    type: 'scatter',
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
        const refName = ref ? (ref.fontName + (ref.master ? ` - ${ref.master}` : '')) : '';
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

function highlightFont(fontName) {
    const chartDiv = document.getElementById('chartContainer');
    if (!chartDiv || !chartDiv.data) return;

    const traceCount = chartDiv.data.length;
    if (traceCount === 0) return;

    // Highlight all traces that belong to this font
    const opacities = chartDiv.data.map(trace =>
        trace.name === fontName || trace.name.startsWith(`${fontName} - `) ? 1 : 0.1
    );
    Plotly.restyle('chartContainer', { opacity: opacities });
}

function setReference(fontName, masterName) {
    // Toggle reference off if clicking the same one
    if (state.referenceTrace?.fontName === fontName && state.referenceTrace?.master === masterName) {
        state.referenceTrace = null;
    } else {
        state.referenceTrace = { fontName, master: masterName };
    }
    renderFontList();
    updateChart();
}

function getFirstEnabledMaster() {
    for (const font of state.addedFonts) {
        for (const master of font.masters) {
            if (font.enabledMasters.has(master)) {
                return { fontName: font.name, master };
            }
        }
    }
    return null;
}

// Event handlers
async function handleAddFont(fontName, modalItem) {
    if (state.addedFonts.some(f => f.name === fontName)) {
        return;
    }

    // Mark modal item as loading
    modalItem.classList.add('loading');
    modalItem.innerHTML = `${icons.spinner} ${fontName}`;

    try {
        const charset = elements.charsetSelect.value;
        const fontData = await fetchGrayscaleData(fontName, charset);

        state.fontData.set(fontName, fontData);
        state.addedFonts.push({
            name: fontName,
            masters: fontData.masters,
            enabledMasters: new Set(fontData.masters),
            enabled: true,
            color: getNextFontColor(),
        });

        renderFontList();
        updateChart();

        // Mark as added (keep disabled)
        modalItem.innerHTML = `✓ ${fontName}`;
        modalItem.classList.remove('loading');
        modalItem.classList.add('added');
    } catch (error) {
        console.error('Failed to load font:', error);
        // Restore item on error
        modalItem.classList.remove('loading');
        modalItem.textContent = fontName;
    }
}

function handleFontToggle(e) {
    const fontIndex = parseInt(e.target.dataset.font);
    const font = state.addedFonts[fontIndex];
    font.enabled = e.target.checked;

    if (font.enabled) {
        font.enabledMasters = new Set(font.masters);
    } else {
        font.enabledMasters.clear();
    }

    renderFontList();
    updateChart();
}

function handleMasterToggle(e) {
    const fontIndex = parseInt(e.target.dataset.font);
    const masterName = e.target.dataset.master;
    const font = state.addedFonts[fontIndex];

    if (e.target.checked) {
        font.enabledMasters.add(masterName);
    } else {
        font.enabledMasters.delete(masterName);
    }

    font.enabled = font.enabledMasters.size === font.masters.length;
    renderFontList();
    updateChart();
}

function handleFontRemove(e) {
    const fontIndex = parseInt(e.currentTarget.dataset.font);
    const fontName = state.addedFonts[fontIndex].name;
    state.addedFonts.splice(fontIndex, 1);
    state.fontData.delete(fontName);
    renderFontList();
    updateChart();
}

function openFontModal() {
    const addedNames = new Set(state.addedFonts.map(f => f.name));

    if (state.availableFonts.length === 0) {
        elements.fontModalList.innerHTML = '<div class="no-fonts">没有可用字体</div>';
    } else {
        elements.fontModalList.innerHTML = state.availableFonts.map(font => {
            const isAdded = addedNames.has(font);
            const className = isAdded ? 'modal-item added' : 'modal-item';
            const content = isAdded ? `✓ ${font}` : font;
            return `<div class="${className}" data-font="${font}">${content}</div>`;
        }).join('');

        elements.fontModalList.querySelectorAll('.modal-item:not(.added)').forEach(item => {
            item.addEventListener('click', () => handleAddFont(item.dataset.font, item));
        });
    }

    elements.fontModal.classList.add('active');
}

async function handleCharsetChange() {
    const newCharset = elements.charsetSelect.value;
    if (newCharset === state.currentCharset) return;

    state.currentCharset = newCharset;

    if (state.addedFonts.length === 0) return;

    try {
        // Reload data for all fonts with new charset
        const reloadPromises = state.addedFonts.map(async (font) => {
            const fontData = await fetchGrayscaleData(font.name, newCharset);
            state.fontData.set(font.name, fontData);

            // Update font masters if they changed
            font.masters = fontData.masters;
            // Keep only masters that still exist
            font.enabledMasters = new Set(
                [...font.enabledMasters].filter(m => fontData.masters.includes(m))
            );
            // If no masters enabled, enable all
            if (font.enabledMasters.size === 0) {
                font.enabledMasters = new Set(fontData.masters);
            }
            font.enabled = font.enabledMasters.size === font.masters.length;
        });

        await Promise.all(reloadPromises);
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
    // Set initial charset from select
    state.currentCharset = elements.charsetSelect.value;

    try {
        state.availableFonts = await fetchAvailableFonts();
    } catch (error) {
        console.error('Failed to load available fonts:', error);
    }

    // Event listeners
    elements.addFontBtn.addEventListener('click', openFontModal);
    elements.modalClose.addEventListener('click', () => elements.fontModal.classList.remove('active'));
    elements.fontModal.addEventListener('click', (e) => {
        if (e.target === elements.fontModal) elements.fontModal.classList.remove('active');
    });
    elements.charsetSelect.addEventListener('change', handleCharsetChange);
    elements.binSizeInput.addEventListener('change', handleBinSizeChange);

    document.querySelectorAll('.chart-type-btn').forEach(btn => {
        btn.addEventListener('click', handleChartTypeChange);
    });
}

init();
