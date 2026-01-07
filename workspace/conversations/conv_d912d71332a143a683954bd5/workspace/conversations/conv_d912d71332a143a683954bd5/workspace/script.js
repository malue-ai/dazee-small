// ========== 全局变量 ==========
const coursesData = [
    {
        id: 1,
        title: 'Python AI 基础',
        category: 'beginner',
        level: '入门',
        duration: '8 weeks',
        students: 2340,
        rating: 4.9,
        instructor: '张教授',
        description: '从零开始学习 Python 编程和 AI 基础',
        image: 'https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=400&h=250&fit=crop',
        tags: ['Python', 'AI基础', '编程入门']
    },
    {
        id: 2,
        title: '机器学习算法',
        category: 'intermediate',
        level: '进阶',
        duration: '10 weeks',
        students: 1850,
        rating: 4.8,
        instructor: '李博士',
        description: '深入理解机器学习核心算法原理',
        image: 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=400&h=250&fit=crop',
        tags: ['机器学习', '算法', '数学']
    },
    {
        id: 3,
        title: '深度学习与神经网络',
        category: 'advanced',
        level: '高级',
        duration: '12 weeks',
        students: 1420,
        rating: 5.0,
        instructor: '王教授',
        description: '掌握深度学习前沿技术和应用',
        image: 'https://images.unsplash.com/photo-1620712943543-bcc4688e7485?w=400&h=250&fit=crop',
        tags: ['深度学习', 'CNN', 'RNN']
    },
    {
        id: 4,
        title: '自然语言处理',
        category: 'advanced',
        level: '高级',
        duration: '10 weeks',
        students: 980,
        rating: 4.9,
        instructor: '刘博士',
        description: '掌握 NLP 技术和大模型应用',
        image: 'https://images.unsplash.com/photo-1677442136019-21780ecad995?w=400&h=250&fit=crop',
        tags: ['NLP', 'Transformer', 'LLM']
    },
    {
        id: 5,
        title: '计算机视觉',
        category: 'advanced',
        level: '高级',
        duration: '11 weeks',
        students: 1120,
        rating: 4.8,
        instructor: '陈教授',
        description: '图像识别和视觉理解技术',
        image: 'https://images.unsplash.com/photo-1535378917042-10a22c95931a?w=400&h=250&fit=crop',
        tags: ['CV', '图像识别', 'YOLO']
    },
    {
        id: 6,
        title: 'AI 数据处理',
        category: 'beginner',
        level: '入门',
        duration: '6 weeks',
        students: 1680,
        rating: 4.7,
        instructor: '赵老师',
        description: '学习数据清洗、预处理和特征工程',
        image: 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=400&h=250&fit=crop',
        tags: ['数据处理', 'Pandas', 'NumPy']
    }
];

let currentFilter = 'all';
let darkMode = false;

// ========== DOM 元素 ==========
const themeToggle = document.getElementById('themeToggle');
const navLinks = document.querySelectorAll('.nav-link');
const coursesGrid = document.getElementById('coursesGrid');
const filterBtns = document.querySelectorAll('.filter-btn');
const pathCards = document.querySelectorAll('.path-card');
const assistantToggle = document.getElementById('assistantToggle');
const assistantWindow = document.getElementById('assistantWindow');
const assistantClose = document.getElementById('assistantClose');
const assistantInput = document.getElementById('assistantInput');
const sendMessage = document.getElementById('sendMessage');
const assistantMessages = document.getElementById('assistantMessages');
const suggestionBtns = document.querySelectorAll('.suggestion-btn');

// ========== 初始化 ==========
document.addEventListener('DOMContentLoaded', () => {
    renderCourses();
    initTheme();
    initNavigation();
    initFilters();
    initPathCards();
    initAssistant();
    initAnimations();
});

// ========== 主题切换 ==========
function initTheme() {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
        enableDarkMode();
    }
}

themeToggle.addEventListener('click', () => {
    if (darkMode) {
        disableDarkMode();
    } else {
        enableDarkMode();
    }
});

function enableDarkMode() {
    document.documentElement.setAttribute('data-theme', 'dark');
    themeToggle.innerHTML = '<i class="fas fa-sun"></i>';
    darkMode = true;
    localStorage.setItem('theme', 'dark');
}

function disableDarkMode() {
    document.documentElement.removeAttribute('data-theme');
    themeToggle.innerHTML = '<i class="fas fa-moon"></i>';
    darkMode = false;
    localStorage.setItem('theme', 'light');
}

// ========== 导航 ==========
function initNavigation() {
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            
            // 移除所有 active 类
            navLinks.forEach(l => l.classList.remove('active'));
            
            // 添加 active 类到当前链接
            link.classList.add('active');
            
            // 平滑滚动到对应部分
            const targetId = link.getAttribute('href');
            const targetSection = document.querySelector(targetId);
            
            if (targetSection) {
                const offsetTop = targetSection.offsetTop - 80;
                window.scrollTo({
                    top: offsetTop,
                    behavior: 'smooth'
                });
            }
        });
    });
    
    // 滚动时更新导航高亮
    window.addEventListener('scroll', updateNavOnScroll);
}

function updateNavOnScroll() {
    const sections = document.querySelectorAll('section[id]');
    const scrollY = window.pageYOffset;
    
    sections.forEach(section => {
        const sectionHeight = section.offsetHeight;
        const sectionTop = section.offsetTop - 100;
        const sectionId = section.getAttribute('id');
        
        if (scrollY > sectionTop && scrollY <= sectionTop + sectionHeight) {
            navLinks.forEach(link => {
                link.classList.remove('active');
                if (link.getAttribute('href') === `#${sectionId}`) {
                    link.classList.add('active');
                }
            });
        }
    });
}

// ========== 课程渲染 ==========
function renderCourses(filter = 'all') {
    const filteredCourses = filter === 'all' 
        ? coursesData 
        : coursesData.filter(course => course.category === filter);
    
    coursesGrid.innerHTML = filteredCourses.map(course => `
        <div class="course-card" data-category="${course.category}">
            <div class="course-image" style="background-image: url('${course.image}')">
                <span class="course-level">${course.level}</span>
            </div>
            <div class="course-content">
                <h3>${course.title}</h3>
                <p class="course-description">${course.description}</p>
                <div class="course-tags">
                    ${course.tags.map(tag => `<span class="tag">${tag}</span>`).join('')}
                </div>
                <div class="course-meta">
                    <div class="course-instructor">
                        <i class="fas fa-user-tie"></i>
                        <span>${course.instructor}</span>
                    </div>
                    <div class="course-stats">
                        <span><i class="fas fa-clock"></i> ${course.duration}</span>
                        <span><i class="fas fa-users"></i> ${course.students}</span>
                        <span><i class="fas fa-star"></i> ${course.rating}</span>
                    </div>
                </div>
                <button class="btn-course" onclick="enrollCourse(${course.id})">
                    立即学习
                </button>
            </div>
        </div>
    `).join('');
    
    // 添加课程卡片样式（如果CSS中没有）
    addCourseCardStyles();
}

function addCourseCardStyles() {
    if (!document.getElementById('course-card-styles')) {
        const style = document.createElement('style');
        style.id = 'course-card-styles';
        style.textContent = `
            .course-card {
                background: var(--bg-primary);
                border: 2px solid var(--border-color);
                border-radius: 20px;
                overflow: hidden;
                transition: var(--transition);
                cursor: pointer;
            }
            
            .course-card:hover {
                transform: translateY(-8px);
                box-shadow: var(--shadow-xl);
                border-color: var(--primary-color);
            }
            
            .course-image {
                height: 200px;
                background-size: cover;
                background-position: center;
                position: relative;
                display: flex;
                align-items: flex-start;
                justify-content: flex-end;
                padding: 1rem;
            }
            
            .course-level {
                background: rgba(255, 255, 255, 0.95);
                padding: 0.5rem 1rem;
                border-radius: 8px;
                font-size: 0.875rem;
                font-weight: 600;
                color: var(--primary-color);
            }
            
            .course-content {
                padding: 1.5rem;
            }
            
            .course-content h3 {
                font-size: 1.25rem;
                margin-bottom: 0.75rem;
            }
            
            .course-description {
                color: var(--text-secondary);
                margin-bottom: 1rem;
                font-size: 0.95rem;
            }
            
            .course-tags {
                display: flex;
                flex-wrap: wrap;
                gap: 0.5rem;
                margin-bottom: 1rem;
            }
            
            .course-meta {
                margin-bottom: 1rem;
                padding-bottom: 1rem;
                border-bottom: 1px solid var(--border-color);
            }
            
            .course-instructor {
                display: flex;
                align-items: center;
                gap: 0.5rem;
                margin-bottom: 0.75rem;
                color: var(--text-secondary);
            }
            
            .course-stats {
                display: flex;
                gap: 1rem;
                font-size: 0.875rem;
                color: var(--text-secondary);
            }
            
            .course-stats span {
                display: flex;
                align-items: center;
                gap: 0.25rem;
            }
            
            .btn-course {
                width: 100%;
                background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
                color: white;
                border: none;
                padding: 0.75rem;
                border-radius: 10px;
                font-weight: 600;
                cursor: pointer;
                transition: var(--transition);
            }
            
            .btn-course:hover {
                transform: scale(1.02);
                box-shadow: var(--shadow-lg);
            }
        `;
        document.head.appendChild(style);
    }
}

// ========== 课程筛选 ==========
function initFilters() {
    filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // 移除所有 active 类
            filterBtns.forEach(b => b.classList.remove('active'));
            
            // 添加 active 类到当前按钮
            btn.classList.add('active');
            
            // 获取筛选类别
            const filter = btn.getAttribute('data-filter');
            currentFilter = filter;
            
            // 渲染筛选后的课程
            renderCourses(filter);
            
            // 添加动画效果
            animateCourseCards();
        });
    });
}

function animateCourseCards() {
    const cards = document.querySelectorAll('.course-card');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            card.style.transition = 'all 0.5s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });
}

// ========== 学习路径 ==========
function initPathCards() {
    pathCards.forEach(card => {
        card.addEventListener('click', () => {
            const path = card.getAttribute('data-path');
            showPathModal(path);
        });
    });
}

function showPathModal(path) {
    const pathInfo = {
        beginner: {
            title: 'AI入门学习路径',
            description: '适合零基础学习者，循序渐进掌握AI基础',
            steps: [
                '第1阶段：Python编程基础（2周）',
                '第2阶段：数学基础（线性代数、概率论）（3周）',
                '第3阶段：AI概念与应用（2周）',
                '第4阶段：简单项目实战（3周）'
            ]
        },
        intermediate: {
            title: '机器学习学习路径',
            description: '深入学习机器学习算法和应用',
            steps: [
                '第1阶段：监督学习算法（4周）',
                '第2阶段：无监督学习（3周）',
                '第3阶段：特征工程（2周）',
                '第4阶段：模型评估与优化（3周）',
                '第5阶段：实战项目（4周）'
            ]
        },
        advanced: {
            title: '深度学习学习路径',
            description: '掌握深度学习前沿技术',
            steps: [
                '第1阶段：神经网络基础（3周）',
                '第2阶段：CNN与图像处理（4周）',
                '第3阶段：RNN与序列模型（4周）',
                '第4阶段：Transformer架构（3周）',
                '第5阶段：大模型应用（4周）'
            ]
        },
        specialized: {
            title: '专项应用学习路径',
            description: '聚焦特定领域的AI应用',
            steps: [
                '选择方向：NLP / CV / Agent',
                '第1阶段：领域基础知识（4周）',
                '第2阶段：核心技术深入（5周）',
                '第3阶段：工具与框架（3周）',
                '第4阶段：项目实战（6周）'
            ]
        }
    };
    
    const info = pathInfo[path];
    alert(`${info.title}\n\n${info.description}\n\n学习计划：\n${info.steps.join('\n')}\n\n点击"开始学习"按钮开始你的学习之旅！`);
}

// ========== AI助手 ==========
function initAssistant() {
    // 切换助手窗口
    assistantToggle.addEventListener('click', () => {
        assistantWindow.classList.toggle('active');
    });
    
    // 关闭助手窗口
    assistantClose.addEventListener('click', () => {
        assistantWindow.classList.remove('active');
    });
    
    // 发送消息
    sendMessage.addEventListener('click', sendUserMessage);
    
    assistantInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendUserMessage();
        }
    });
    
    // 快捷建议按钮
    suggestionBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const message = btn.textContent;
            handleSuggestion(message);
        });
    });
}

function sendUserMessage() {
    const message = assistantInput.value.trim();
    
    if (message === '') return;
    
    // 添加用户消息
    addMessage(message, 'user');
    
    // 清空输入框
    assistantInput.value = '';
    
    // 模拟AI回复
    setTimeout(() => {
        const reply = generateAIReply(message);
        addMessage(reply, 'bot');
    }, 1000);
}

function addMessage(content, type) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}-message`;
    
    if (type === 'bot') {
        messageDiv.innerHTML = `
            <div class="message-avatar">
                <i class="fas fa-robot"></i>
            </div>
            <div class="message-content">
                <p>${content}</p>
            </div>
        `;
    } else {
        messageDiv.innerHTML = `
            <div class="message-avatar">
                <i class="fas fa-user"></i>
            </div>
            <div class="message-content">
                <p>${content}</p>
            </div>
        `;
    }
    
    assistantMessages.appendChild(messageDiv);
    assistantMessages.scrollTop = assistantMessages.scrollHeight;
}

function generateAIReply(message) {
    const lowerMessage = message.toLowerCase();
    
    if (lowerMessage.includes('推荐') || lowerMessage.includes('课程')) {
        return '根据你的学习进度，我推荐你先学习"Python AI 基础"课程，然后进阶到"机器学习算法"。这两门课程会为你打下坚实的基础！';
    } else if (lowerMessage.includes('学习') || lowerMessage.includes('建议')) {
        return '建议你每天学习1-2小时，保持连续学习。可以从入门课程开始，完成理论学习后立即进行实践项目巩固知识。有问题随时问我！';
    } else if (lowerMessage.includes('项目') || lowerMessage.includes('实战')) {
        return '我们有丰富的实战项目供你选择！推荐从"手写数字识别"开始，这是一个经典的入门项目。完成后可以尝试"情感分析系统"等进阶项目。';
    } else if (lowerMessage.includes('困难') || lowerMessage.includes('问题')) {
        return '学习AI确实有挑战，但不要担心！我建议你：1) 从基础开始，不要跳步；2) 多做实践项目；3) 加入学习社区交流；4) 遇到问题及时提问。我会一直陪伴你！';
    } else {
        return '我是你的AI学习助手，可以帮你推荐课程、解答疑问、提供学习建议。你可以问我关于课程、项目、学习方法等任何问题！';
    }
}

function handleSuggestion(suggestion) {
    addMessage(suggestion, 'user');
    
    setTimeout(() => {
        let reply = '';
        
        if (suggestion.includes('推荐课程')) {
            reply = '根据当前AI领域的热门方向，我为你推荐以下学习路径：\n\n1. 基础阶段：Python AI 基础 + AI 数据处理\n2. 进阶阶段：机器学习算法\n3. 高级阶段：深度学习与神经网络\n4. 专项突破：选择 NLP 或 CV 方向深入学习\n\n每个阶段都配有实战项目，帮助你巩固所学知识！';
        } else if (suggestion.includes('解答疑问')) {
            reply = '我可以帮你解答以下问题：\n\n• 课程内容和难度\n• 学习路径规划\n• 技术概念解释\n• 项目实战指导\n• 学习资源推荐\n\n请告诉我你想了解什么？';
        } else if (suggestion.includes('学习建议')) {
            reply = '根据学习数据分析，这里有一些提升学习效果的建议：\n\n✅ 每天保持1-2小时学习时间\n✅ 理论学习后立即实践\n✅ 定期复习巩固知识\n✅ 加入学习小组互相激励\n✅ 记录学习笔记和心得\n\n坚持下去，你一定能掌握AI技术！';
        }
        
        addMessage(reply, 'bot');
    }, 1000);
}

// ========== 课程注册 ==========
function enrollCourse(courseId) {
    const course = coursesData.find(c => c.id === courseId);
    
    if (course) {
        alert(`恭喜你！已成功加入《${course.title}》课程\n\n讲师：${course.instructor}\n时长：${course.duration}\n\n请前往"我的学习"页面开始学习！`);
        
        // 更新学习进度
        updateLearningProgress();
    }
}

// ========== 动画效果 ==========
function initAnimations() {
    // 监听滚动事件，添加元素进入视口动画
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -100px 0px'
    };
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, observerOptions);
    
    // 观察所有需要动画的元素
    const animateElements = document.querySelectorAll('.path-card, .practice-card, .progress-card');
    
    animateElements.forEach(el => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(30px)';
        el.style.transition = 'all 0.6s ease-out';
        observer.observe(el);
    });
}

// ========== 学习进度更新 ==========
function updateLearningProgress() {
    // 模拟更新进度数据
    console.log('学习进度已更新');
    
    // 可以在这里添加实际的进度更新逻辑
    // 例如：调用后端API、更新localStorage等
}

// ========== 开始学习按钮 ==========
document.getElementById('startLearning')?.addEventListener('click', () => {
    // 滚动到学习路径部分
    const learningPath = document.getElementById('learning-path');
    if (learningPath) {
        const offsetTop = learningPath.offsetTop - 80;
        window.scrollTo({
            top: offsetTop,
            behavior: 'smooth'
        });
    }
});

// ========== 实践项目按钮 ==========
const practiceBtns = document.querySelectorAll('.btn-practice');
practiceBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
        const card = e.target.closest('.practice-card');
        const title = card.querySelector('h3').textContent;
        alert(`准备开始实战项目：${title}\n\n项目环境正在准备中...\n\n即将跳转到项目实战页面！`);
    });
});

// ========== 登录按钮 ==========
document.getElementById('loginBtn')?.addEventListener('click', () => {
    alert('登录功能开发中...\n\n敬请期待！');
});

// ========== 工具函数 ==========
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// 使用防抖优化滚动事件
window.addEventListener('scroll', debounce(() => {
    // 可以在这里添加滚动相关的优化逻辑
}, 100));

console.log('🎉 AI学习平台已成功加载！');
console.log('📚 课程总数：', coursesData.length);
console.log('✨ 开始你的AI学习之旅吧！');
