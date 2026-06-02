window.PaginationUtils = (function() {
    var DEFAULT_PAGE_SIZE = 20;
    var PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

    function createPagination(containerId, options) {
        var container = document.getElementById(containerId);
        if (!container) return null;

        options = options || {};
        var pageSize = options.pageSize || DEFAULT_PAGE_SIZE;
        var pageSizeOptions = options.pageSizeOptions || PAGE_SIZE_OPTIONS;
        var onPageChange = options.onPageChange || function() {};
        var total = options.total || 0;

        var state = {
            currentPage: 1,
            pageSize: pageSize,
            total: total
        };

        function render() {
            var totalPages = Math.ceil(state.total / state.pageSize) || 1;
            if (state.currentPage > totalPages) state.currentPage = totalPages;
            if (state.currentPage < 1) state.currentPage = 1;

            var startItem = state.total > 0 ? (state.currentPage - 1) * state.pageSize + 1 : 0;
            var endItem = Math.min(state.currentPage * state.pageSize, state.total);

            var html = '<div class="pagination-wrapper">';

            html += '<div class="pagination-info">';
            html += '共 <span>' + state.total + '</span> 条记录，';
            html += '显示第 <span>' + startItem + '</span>-<span>' + endItem + '</span> 条';
            html += '</div>';

            html += '<div class="pagination-size-selector">';
            html += '<label>每页</label>';
            html += '<select class="form-select form-select-sm" id="' + containerId + '-pageSize">';
            pageSizeOptions.forEach(function(size) {
                html += '<option value="' + size + '"' + (size === state.pageSize ? ' selected' : '') + '>' + size + '</option>';
            });
            html += '</select>';
            html += '<label>条</label>';
            html += '</div>';

            html += '<div class="pagination-nav">';
            html += '<ul class="pagination mb-0">';

            html += '<li class="page-item' + (state.currentPage <= 1 ? ' disabled' : '') + '">';
            html += '<a class="page-link" href="#" data-page="' + (state.currentPage - 1) + '" aria-label="上一页"><i class="bi bi-chevron-left"></i></a>';
            html += '</li>';

            var pages = getPageNumbers(state.currentPage, totalPages);
            pages.forEach(function(p) {
                if (p === '...') {
                    html += '<li class="page-item disabled"><span class="page-link">...</span></li>';
                } else {
                    html += '<li class="page-item' + (p === state.currentPage ? ' active' : '') + '">';
                    html += '<a class="page-link" href="#" data-page="' + p + '">' + p + '</a>';
                    html += '</li>';
                }
            });

            html += '<li class="page-item' + (state.currentPage >= totalPages ? ' disabled' : '') + '">';
            html += '<a class="page-link" href="#" data-page="' + (state.currentPage + 1) + '" aria-label="下一页"><i class="bi bi-chevron-right"></i></a>';
            html += '</li>';

            html += '</ul>';
            html += '</div>';
            html += '</div>';

            container.innerHTML = html;
            bindEvents();
        }

        function getPageNumbers(current, total) {
            if (total <= 7) {
                var arr = [];
                for (var i = 1; i <= total; i++) arr.push(i);
                return arr;
            }

            var pages = [];
            pages.push(1);

            if (current > 4) {
                pages.push('...');
            }

            var start = Math.max(2, current - 1);
            var end = Math.min(total - 1, current + 1);

            if (current <= 4) {
                start = 2;
                end = 5;
            }

            if (current >= total - 3) {
                start = total - 4;
                end = total - 1;
            }

            for (var j = start; j <= end; j++) {
                pages.push(j);
            }

            if (current < total - 3) {
                pages.push('...');
            }

            pages.push(total);

            return pages;
        }

        function bindEvents() {
            var pageLinks = container.querySelectorAll('.page-link[data-page]');
            pageLinks.forEach(function(link) {
                link.addEventListener('click', function(e) {
                    e.preventDefault();
                    var page = parseInt(this.getAttribute('data-page'));
                    var totalPages = Math.ceil(state.total / state.pageSize) || 1;
                    if (page < 1 || page > totalPages) return;
                    state.currentPage = page;
                    onPageChange(state.currentPage, state.pageSize);
                    render();
                });
            });

            var sizeSelect = document.getElementById(containerId + '-pageSize');
            if (sizeSelect) {
                sizeSelect.addEventListener('change', function() {
                    state.pageSize = parseInt(this.value);
                    state.currentPage = 1;
                    onPageChange(state.currentPage, state.pageSize);
                    render();
                });
            }
        }

        function setTotal(newTotal) {
            state.total = newTotal;
            render();
        }

        function setPage(page) {
            state.currentPage = page;
            render();
        }

        function getState() {
            return {
                currentPage: state.currentPage,
                pageSize: state.pageSize,
                total: state.total,
                offset: (state.currentPage - 1) * state.pageSize
            };
        }

        render();

        return {
            setTotal: setTotal,
            setPage: setPage,
            getState: getState,
            render: render
        };
    }

    function paginateArray(array, page, pageSize) {
        page = page || 1;
        pageSize = pageSize || DEFAULT_PAGE_SIZE;
        var start = (page - 1) * pageSize;
        var end = start + pageSize;
        return array.slice(start, end);
    }

    return {
        createPagination: createPagination,
        paginateArray: paginateArray,
        DEFAULT_PAGE_SIZE: DEFAULT_PAGE_SIZE
    };
})();
