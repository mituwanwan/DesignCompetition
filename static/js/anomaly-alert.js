window.AnomalyAlert = (function() {
    var alertElements = [];

    function highlightElement(element, options) {
        options = options || {};

        if (typeof element === 'string') {
            element = document.querySelector(element);
        }
        if (!element) return;

        var level = options.level || 'danger';
        var pulse = options.pulse !== undefined ? options.pulse : true;
        var icon = options.icon !== undefined ? options.icon : true;

        var colors = {
            danger: { bg: 'rgba(201, 97, 97, 0.12)', border: '#C96161', text: '#A74040' },
            warning: { bg: 'rgba(229, 169, 84, 0.12)', border: '#E5A954', text: '#C38732' },
            info: { bg: 'rgba(87, 163, 163, 0.12)', border: '#57A3A3', text: '#358383' }
        };

        var colorSet = colors[level] || colors.danger;

        element.style.backgroundColor = colorSet.bg;
        element.style.borderLeft = '4px solid ' + colorSet.border;
        element.style.color = colorSet.text;
        element.style.transition = 'all 0.3s ease';
        element.classList.add('anomaly-highlight', 'anomaly-' + level);

        if (pulse) {
            element.classList.add('anomaly-pulse');
        }

        if (icon) {
            var iconMap = {
                danger: 'bi-exclamation-triangle-fill',
                warning: 'bi-exclamation-circle-fill',
                info: 'bi-info-circle-fill'
            };
            var iconEl = document.createElement('i');
            iconEl.className = 'bi ' + (iconMap[level] || iconMap.danger) + ' anomaly-icon';
            iconEl.style.color = colorSet.border;
            iconEl.style.marginRight = '6px';
            iconEl.style.fontSize = '0.9em';
            element.insertBefore(iconEl, element.firstChild);
        }

        alertElements.push(element);
    }

    function highlightValue(element, threshold, options) {
        options = options || {};

        if (typeof element === 'string') {
            element = document.querySelector(element);
        }
        if (!element) return;

        var value = parseFloat(element.textContent.replace(/[^0-9.\-]/g, ''));
        if (isNaN(value)) return;

        var isAbnormal = false;
        var level = 'danger';

        if (options.min !== undefined && value < options.min) {
            isAbnormal = true;
            level = options.minLevel || 'warning';
        }
        if (options.max !== undefined && value > options.max) {
            isAbnormal = true;
            level = options.maxLevel || 'danger';
        }
        if (options.check && options.check(value)) {
            isAbnormal = true;
            level = options.checkLevel || 'danger';
        }

        if (isAbnormal) {
            highlightElement(element, {
                level: level,
                pulse: options.pulse !== undefined ? options.pulse : true,
                icon: false
            });

            if (options.tooltip) {
                element.title = options.tooltip;
                element.setAttribute('data-bs-toggle', 'tooltip');
                var tooltip = new bootstrap.Tooltip(element, {
                    title: options.tooltip,
                    placement: options.tooltipPlacement || 'top',
                    trigger: 'hover'
                });
            }
        }
    }

    function highlightTableRow(row, level) {
        if (typeof row === 'string') {
            row = document.querySelector(row);
        }
        if (!row) return;

        var colors = {
            danger: { bg: 'rgba(201, 97, 97, 0.08)', border: '#C96161' },
            warning: { bg: 'rgba(229, 169, 84, 0.08)', border: '#E5A954' },
            info: { bg: 'rgba(87, 163, 163, 0.08)', border: '#57A3A3' }
        };

        var colorSet = colors[level] || colors.danger;
        row.style.backgroundColor = colorSet.bg;
        row.style.borderLeft = '3px solid ' + colorSet.border;
        row.classList.add('anomaly-row', 'anomaly-row-' + level);
    }

    function scanTable(tableSelector, rules) {
        var table = document.querySelector(tableSelector);
        if (!table) return;

        var rows = table.querySelectorAll('tbody tr');
        rows.forEach(function(row) {
            rules.forEach(function(rule) {
                var cell = row.querySelector(rule.cellSelector);
                if (!cell) return;

                var value = parseFloat(cell.textContent.replace(/[^0-9.\-]/g, ''));
                if (isNaN(value)) return;

                var isAbnormal = false;
                var level = rule.level || 'danger';

                if (rule.min !== undefined && value < rule.min) isAbnormal = true;
                if (rule.max !== undefined && value > rule.max) isAbnormal = true;
                if (rule.check && rule.check(value)) isAbnormal = true;

                if (isAbnormal) {
                    highlightTableRow(row, level);
                    if (rule.highlightCell) {
                        cell.style.fontWeight = '700';
                        cell.style.color = level === 'danger' ? '#C96161' : level === 'warning' ? '#E5A954' : '#57A3A3';
                    }
                }
            });
        });
    }

    function clearAll() {
        alertElements.forEach(function(el) {
            if (!el) return;
            el.style.backgroundColor = '';
            el.style.borderLeft = '';
            el.style.color = '';
            el.classList.remove('anomaly-highlight', 'anomaly-pulse', 'anomaly-danger', 'anomaly-warning', 'anomaly-info');

            var icon = el.querySelector('.anomaly-icon');
            if (icon) icon.remove();
        });
        alertElements = [];
    }

    function checkHealthData(healthValues) {
        var rules = {
            temperature: { min: 36, max: 37.3, unit: '℃', name: '体温' },
            heart_rate: { min: 60, max: 100, unit: 'bpm', name: '心率' },
            systolic_pressure: { min: 90, max: 140, unit: 'mmHg', name: '收缩压' },
            diastolic_pressure: { min: 60, max: 90, unit: 'mmHg', name: '舒张压' },
            blood_sugar: { min: 3.9, max: 11.1, unit: 'mmol/L', name: '血糖' }
        };

        var anomalies = [];

        Object.keys(healthValues).forEach(function(key) {
            var rule = rules[key];
            if (!rule) return;

            var value = parseFloat(healthValues[key]);
            if (isNaN(value)) return;

            var isAbnormal = false;
            var direction = '';

            if (value < rule.min) {
                isAbnormal = true;
                direction = '偏低';
            }
            if (value > rule.max) {
                isAbnormal = true;
                direction = '偏高';
            }

            if (isAbnormal) {
                anomalies.push({
                    key: key,
                    name: rule.name,
                    value: value,
                    unit: rule.unit,
                    direction: direction,
                    normalRange: rule.min + '-' + rule.max,
                    level: key === 'temperature' || key === 'heart_rate' ? 'danger' : 'warning'
                });
            }
        });

        return anomalies;
    }

    return {
        highlightElement: highlightElement,
        highlightValue: highlightValue,
        highlightTableRow: highlightTableRow,
        scanTable: scanTable,
        clearAll: clearAll,
        checkHealthData: checkHealthData
    };
})();
