module.exports = {
  apps: [
    {
      name: 'deerflow',         // 你希望显示的应用名称
      script: 'make',          // 要执行的命令
      args: 'start',           // 命令的参数
      instances: 1,            // 启动的实例数
      autorestart: true,       // 崩溃时自动重启
      watch: false,            // 生产环境建议关闭文件监听
      max_memory_restart: '1G', // 内存使用超过1G时重启（可选）
      env: {
        NODE_ENV: 'production',
        DEER_FLOW_PROD_FRONTEND: '1',
        DEER_FLOW_NO_NGINX: '1',
        SKIP_LANGGRAPH_SERVER: '1',
      },
    },
  ],
};
