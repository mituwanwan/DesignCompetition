window.ChartUtils = (function() {
    var COLORS = {
        blue: '#5B8DB8',
        blueLight: '#8BB3D4',
        green: '#68A357',
        greenLight: '#8BC47A',
        orange: '#E5A954',
        orangeLight: '#F0C78A',
        red: '#C96161',
        redLight: '#E08585',
        purple: '#8B7DB8',
        purpleLight: '#B0A6D4',
        teal: '#57A3A3',
        tealLight: '#7AC4C4',
        pink: '#C97B8B',
        yellow: '#D4C054',
        gray: '#9B938A',
        grayLight: '#BAB3AA',
        warm: '#D4A574',
        textPrimary: '#4A4540',
        textSecondary: '#6B635A',
        textMuted: '#BAB3AA',
        border: '#E5DFD5',
        bgLight: '#FAF7F2',
        successSoft: 'rgba(104, 163, 87, 0.12)',
        dangerSoft: 'rgba(201, 97, 97, 0.12)',
        warningSoft: 'rgba(229, 169, 84, 0.12)',
        infoSoft: 'rgba(87, 163, 163, 0.12)'
    };

    var PALETTE = [COLORS.blue, COLORS.green, COLORS.orange, COLORS.red, COLORS.purple, COLORS.teal, COLORS.pink, COLORS.yellow, COLORS.gray, COLORS.warm];

    function getBaseLayout(options) {
        options = options || {};
        var title = options.title || '';
        var yTitle = options.yTitle || '';
        var yTitle2 = options.yTitle2 || '';
        var height = options.height || 320;

        var layout = {
            title: {
                text: title,
                font: { size: 14, color: COLORS.textPrimary, family: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif' },
                x: 0.02,
                xanchor: 'left',
                pad: { t: 5, b: 5 }
            },
            margin: { t: title ? 40 : 20, r: yTitle2 ? 60 : 25, b: 55, l: 60 },
            height: height,
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: {
                family: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif',
                size: 11,
                color: COLORS.textSecondary
            },
            xaxis: {
                title: '',
                tickfont: { size: 10, color: COLORS.textMuted },
                gridcolor: 'rgba(229, 223, 213, 0.5)',
                gridwidth: 1,
                zeroline: false,
                linecolor: COLORS.border,
                linewidth: 1
            },
            yaxis: {
                title: {
                    text: yTitle,
                    font: { size: 11, color: COLORS.textSecondary },
                    standoff: 10
                },
                tickfont: { size: 10, color: COLORS.textMuted },
                gridcolor: 'rgba(229, 223, 213, 0.5)',
                gridwidth: 1,
                zeroline: false,
                linecolor: COLORS.border,
                linewidth: 1
            },
            legend: {
                orientation: 'h',
                y: -0.18,
                x: 0.5,
                xanchor: 'center',
                font: { size: 11, color: COLORS.textSecondary },
                bgcolor: 'rgba(0,0,0,0)',
                borderwidth: 0
            },
            hovermode: 'x unified',
            hoverlabel: {
                bgcolor: '#fff',
                bordercolor: COLORS.border,
                font: { size: 12, color: COLORS.textPrimary, family: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif' }
            }
        };

        if (yTitle2) {
            layout.yaxis2 = {
                title: {
                    text: yTitle2,
                    font: { size: 11, color: COLORS.textSecondary },
                    standoff: 10
                },
                tickfont: { size: 10, color: COLORS.textMuted },
                gridcolor: 'rgba(0,0,0,0)',
                overlaying: 'y',
                side: 'right',
                zeroline: false
            };
        }

        if (options.xaxisType === 'date') {
            layout.xaxis.tickformat = '%m-%d';
            layout.xaxis.tickangle = -30;
            layout.xaxis.type = 'date';
        }

        if (options.yRange) {
            layout.yaxis.range = options.yRange;
        }

        if (options.barmode) {
            layout.barmode = options.barmode;
        }

        return layout;
    }

    function getConfig() {
        return {
            displayModeBar: true,
            modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
            displaylogo: false,
            responsive: true,
            scrollZoom: true,
            toImageButtonOptions: {
                format: 'png',
                filename: 'chart',
                height: 500,
                width: 900,
                scale: 2
            }
        };
    }

    function makeLineTrace(options) {
        var trace = {
            x: options.x || [],
            y: options.y || [],
            type: 'scatter',
            mode: options.mode || 'lines+markers',
            name: options.name || '',
            line: {
                color: options.color || COLORS.blue,
                width: options.lineWidth || 2.5,
                shape: options.shape || 'spline',
                smoothing: 1.0
            },
            marker: {
                size: options.markerSize || 5,
                color: options.color || COLORS.blue,
                line: options.markerLine ? { width: options.markerLine.width || 1, color: options.markerLine.color || '#fff' } : undefined
            },
            fill: options.fill || undefined,
            fillcolor: options.fillColor || undefined,
            hovertemplate: options.hoverTemplate || '%{x}<br>' + (options.name || '') + ': %{y:.1f}' + (options.unit || '') + '<extra></extra>',
            connectgaps: true
        };

        if (options.yaxis) trace.yaxis = options.yaxis;

        return trace;
    }

    function makeBarTrace(options) {
        var trace = {
            x: options.x || [],
            y: options.y || [],
            type: 'bar',
            name: options.name || '',
            marker: {
                color: options.color || COLORS.blue,
                line: options.border ? { width: 1, color: options.border } : undefined,
                cornerradius: 3
            },
            text: options.showText ? options.y : undefined,
            textposition: options.showText ? 'auto' : undefined,
            textfont: { size: 10, color: COLORS.textSecondary },
            hovertemplate: options.hoverTemplate || '%{x}<br>' + (options.name || '') + ': %{y}' + (options.unit || '') + '<extra></extra>'
        };

        if (options.orientation) trace.orientation = options.orientation;
        if (options.yaxis) trace.yaxis = options.yaxis;

        return trace;
    }

    function makePieTrace(options) {
        return {
            labels: options.labels || [],
            values: options.values || [],
            type: 'pie',
            hole: options.hole !== undefined ? options.hole : 0.45,
            marker: {
                colors: options.colors || PALETTE.slice(0, (options.labels || []).length),
                line: { width: 2, color: '#fff' }
            },
            textinfo: options.textInfo || 'label+percent',
            textposition: 'outside',
            textfont: { size: 11, color: COLORS.textSecondary },
            hovertemplate: '%{label}<br>数量: %{value}<br>占比: %{percent}<extra></extra>',
            pull: options.pull || undefined,
            rotation: options.rotation || 0
        };
    }

    function makeNormalRange(yMin, yMax, color) {
        return {
            type: 'rect',
            xref: 'paper',
            yref: 'y',
            x0: 0,
            x1: 1,
            y0: yMin,
            y1: yMax,
            fillcolor: color || 'rgba(104, 163, 87, 0.08)',
            line: { width: 0 }
        };
    }

    function makeAnnotation(options) {
        return {
            x: options.x,
            y: options.y,
            text: options.text,
            showarrow: options.showArrow !== undefined ? options.showArrow : true,
            arrowhead: 2,
            arrowsize: 0.8,
            arrowwidth: 1,
            arrowcolor: options.color || COLORS.red,
            font: { size: 10, color: options.color || COLORS.red },
            bordercolor: options.color || COLORS.red,
            borderwidth: 1,
            borderpad: 3,
            bgcolor: '#fff',
            opacity: 0.9
        };
    }

    function makeAbnormalMarkerTrace(options) {
        return {
            x: options.x || [],
            y: options.y || [],
            type: 'scatter',
            mode: 'markers',
            name: options.name || '异常值',
            marker: {
                size: 10,
                color: options.color || COLORS.red,
                symbol: 'x',
                line: { width: 2, color: options.color || COLORS.red }
            },
            hovertemplate: '⚠ 异常值<br>%{x}<br>' + (options.name || '') + ': %{y:.1f}' + (options.unit || '') + '<extra></extra>'
        };
    }

    function renderChart(containerId, traces, layout, config) {
        var el = document.getElementById(containerId);
        if (!el) return;

        var finalLayout = Object.assign({}, layout || {});
        if (!finalLayout.shapes) finalLayout.shapes = [];
        if (!finalLayout.annotations) finalLayout.annotations = [];

        Plotly.newPlot(el, traces, finalLayout, config || getConfig());
    }

    function reactChart(containerId, traces, layout, config) {
        var el = document.getElementById(containerId);
        if (!el) return;

        Plotly.react(el, traces, layout || {}, config || getConfig());
    }

    return {
        COLORS: COLORS,
        PALETTE: PALETTE,
        getBaseLayout: getBaseLayout,
        getConfig: getConfig,
        makeLineTrace: makeLineTrace,
        makeBarTrace: makeBarTrace,
        makePieTrace: makePieTrace,
        makeNormalRange: makeNormalRange,
        makeAnnotation: makeAnnotation,
        makeAbnormalMarkerTrace: makeAbnormalMarkerTrace,
        renderChart: renderChart,
        reactChart: reactChart
    };
})();
