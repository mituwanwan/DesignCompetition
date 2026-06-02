/**
 * 消息通知管理器
 * 负责消息通知的轮询、显示和管理
 */

class NotificationManager {
    constructor() {
        this.pollInterval = 10000; // 10秒轮询一次
        this.pollTimer = null;
        this.isPolling = false;
        this.previousMessageCount = -1;  // 消息未读计数（-1表示未初始化）
        this.msgUnreadInitialized = false;
    }

    /**
     * 开始轮询
     */
    startPolling() {
        if (this.isPolling) {
            return;
        }

        this.isPolling = true;
        console.log('消息通知轮询已启动');

        // 立即检查一次
        this.checkUnreadCount();
        this.checkMessageUnreadCount();
        this.loadNotifications();

        // 定时轮询
        this.pollTimer = setInterval(() => {
            this.checkUnreadCount();
            this.checkMessageUnreadCount();
        }, this.pollInterval);
    }

    /**
     * 停止轮询
     */
    stopPolling() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
        this.isPolling = false;
        console.log('消息通知轮询已停止');
    }

    /**
     * 检查未读消息数
     */
    checkUnreadCount() {
        fetch('/api/v1/notifications/unread-count')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.code === 200) {
                    this.updateBadge(data.data.count);
                }
            })
            .catch(error => {
                console.error('检查未读消息数失败:', error);
            });
    }

    /**
     * 更新未读消息徽章
     */
    updateBadge(count) {
        const badge = document.getElementById('notificationBadge');
        if (!badge) return;

        if (count > 0) {
            badge.textContent = count > 99 ? '99+' : count;
            badge.style.display = 'block';

            // 添加动画效果
            badge.classList.add('animate__animated', 'animate__headShake');
            setTimeout(() => {
                badge.classList.remove('animate__animated', 'animate__headShake');
            }, 1000);
        } else {
            badge.style.display = 'none';
        }
    }

    /**
     * 检查留言未读数量（用于侧边栏红点和弹窗）
     */
    checkMessageUnreadCount() {
        fetch('/api/v1/notifications/message-unread-count')
            .then(response => {
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                return response.json();
            })
            .then(data => {
                if (data.code === 200) {
                    const count = data.data.count;
                    // 在首次初始化后，如果 count 增加则弹窗提示
                    if (this.msgUnreadInitialized) {
                        if (count > this.previousMessageCount) {
                            const diff = count - this.previousMessageCount;
                            if (window.showToast) {
                                showToast(`您有${diff}条新留言`, 'info');
                            }
                        }
                    } else {
                        this.msgUnreadInitialized = true;
                    }
                    this.previousMessageCount = count;
                    this.updateSidebarBadge(count);
                }
            })
            .catch(error => {
                console.error('检查留言未读数失败:', error);
            });
    }

    /**
     * 更新侧边栏消息链接的未读红点
     */
    updateSidebarBadge(count) {
        const links = document.querySelectorAll('.sidebar a[href*="/messages"]');
        links.forEach(link => {
            // 移除已有的badge
            const existing = link.querySelector('.sidebar-msg-badge');
            if (existing) existing.remove();

            if (count > 0) {
                const badge = document.createElement('span');
                badge.className = 'badge bg-danger sidebar-msg-badge';
                badge.textContent = count > 99 ? '99+' : count;
                link.appendChild(badge);
            }
        });
    }

    /**
     * 加载消息列表
     */
    loadNotifications(limit = 10) {
        fetch(`/api/v1/notifications?limit=${limit}&unread_only=false`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.code === 200) {
                    this.renderNotifications(data.data.list);
                }
            })
            .catch(error => {
                console.error('加载消息列表失败:', error);
                this.renderError('加载消息失败');
            });
    }

    /**
     * 渲染消息列表
     */
    renderNotifications(notifications) {
        const container = document.getElementById('notificationList');
        if (!container) return;

        if (!notifications || notifications.length === 0) {
            container.innerHTML = `
                <div class="notification-item text-center text-muted py-4">
                    <i class="bi bi-bell fs-4 d-block mb-2"></i>
                    暂无消息
                </div>
            `;
            return;
        }

        let html = '';
        notifications.forEach(notification => {
            const time = this.formatTime(notification.created_at);
            const isUnread = notification.is_read === 0;
            const typeIcon = this.getTypeIcon(notification.type);
            const typeClass = this.getTypeClass(notification.type);

            html += `
                <div class="notification-item ${isUnread ? 'unread' : ''}" data-id="${notification.id}" data-type="${notification.type}">
                    <div class="d-flex">
                        <div class="flex-shrink-0 me-3">
                            <span class="badge ${typeClass}">${typeIcon}</span>
                        </div>
                        <div class="flex-grow-1">
                            <div class="fw-bold">${notification.title}</div>
                            <div class="small">${notification.content}</div>
                            <div class="time mt-1">${time}</div>
                        </div>
                        ${isUnread ? '<div class="flex-shrink-0"><span class="badge bg-danger">新</span></div>' : ''}
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;

        // 绑定点击事件
        this.bindNotificationEvents();
    }

    /**
     * 渲染错误信息
     */
    renderError(message) {
        const container = document.getElementById('notificationList');
        if (!container) return;

        container.innerHTML = `
            <div class="notification-item text-center text-danger py-4">
                <i class="bi bi-exclamation-triangle fs-4 d-block mb-2"></i>
                ${message}
            </div>
        `;
    }

    /**
     * 绑定消息点击事件
     */
    bindNotificationEvents() {
        const items = document.querySelectorAll('.notification-item[data-id]');
        items.forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();

                const notificationId = item.getAttribute('data-id');
                this.markAsRead(notificationId);

                // 触发消息点击行为（根据类型跳转等）
                this.handleNotificationClick(notificationId, item);
            });
        });
    }

    /**
     * 标记消息为已读
     */
    markAsRead(notificationId) {
        fetch(`/api/v1/notifications/${notificationId}/read`, {
            method: 'PUT'
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.code === 200) {
                    // 更新UI
                    const item = document.querySelector(`.notification-item[data-id="${notificationId}"]`);
                    if (item) {
                        item.classList.remove('unread');
                        const badge = item.querySelector('.badge.bg-danger');
                        if (badge) badge.remove();
                    }

                    // 重新检查未读计数
                    this.checkUnreadCount();
                }
            })
            .catch(error => {
                console.error('标记已读失败:', error);
            });
    }

    /**
     * 处理消息点击
     */
    handleNotificationClick(notificationId, element) {
        const role = document.querySelector('meta[name="user-role"]')?.content || '';
        const type = element.querySelector('.badge')?.textContent?.trim() || '';
        const notificationType = element.dataset.type || '';

        let typeStr = '';
        if (element.querySelector('.bi-chat-left-text') || notificationType === 'message') {
            typeStr = 'message';
        } else if (element.querySelector('.bi-exclamation-triangle') || notificationType === 'alarm') {
            typeStr = 'alarm';
        } else if (element.querySelector('.bi-list-task') || notificationType === 'task') {
            typeStr = 'task';
        }

        if (typeStr === 'message') {
            if (role === 'family') {
                window.location.href = '/family/messages';
            } else if (role === 'caregiver') {
                window.location.href = '/caregiver/messages';
            } else {
                window.location.href = '/admin/messages';
            }
            return;
        }

        if (typeStr === 'alarm') {
            if (role === 'admin') {
                window.location.href = '/admin/alarms';
            } else if (role === 'family') {
                window.location.href = '/family/health';
            }
            return;
        }

        if (typeStr === 'task' && role === 'caregiver') {
            window.location.href = '/caregiver/tasks';
            return;
        }

        if (role === 'family') {
            window.location.href = '/family/messages';
        } else if (role === 'caregiver') {
            window.location.href = '/caregiver/messages';
        } else {
            window.location.href = '/admin/messages';
        }
    }

    /**
     * 获取消息类型图标
     */
    getTypeIcon(type) {
        const icons = {
            'alarm': '<i class="bi bi-exclamation-triangle"></i>',
            'task': '<i class="bi bi-list-task"></i>',
            'message': '<i class="bi bi-chat-left-text"></i>'
        };
        return icons[type] || '<i class="bi bi-bell"></i>';
    }

    /**
     * 获取消息类型样式类
     */
    getTypeClass(type) {
        const classes = {
            'alarm': 'bg-danger',
            'task': 'bg-warning text-dark',
            'message': 'bg-info'
        };
        return classes[type] || 'bg-secondary';
    }

    /**
     * 格式化时间
     */
    formatTime(timestamp) {
        if (!timestamp) return '未知时间';

        const date = new Date(timestamp);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) {
            return '刚刚';
        } else if (diffMins < 60) {
            return `${diffMins}分钟前`;
        } else if (diffHours < 24) {
            return `${diffHours}小时前`;
        } else if (diffDays < 7) {
            return `${diffDays}天前`;
        } else {
            return date.toLocaleDateString('zh-CN', {
                month: 'short',
                day: 'numeric'
            });
        }
    }
}

// 创建全局实例
window.notificationManager = new NotificationManager();

// 导出供其他模块使用
if (typeof module !== 'undefined' && module.exports) {
    module.exports = NotificationManager;
}