module.exports = {
  apps: [
    {
      name: "xbox",
      script: "./main.py",
      interpreter: "/Users/yangqian/miniconda3/bin/python",
      cwd: "/Users/yangqian/Downloads/concom",
      exec_mode: "fork",
      instances: 1,
      autorestart: true,
      // 以下退出码视为正常退出，PM2 不会自动重启
      stop_exit_codes: [0],
      max_restarts: 10,
      min_uptime: "10s",
      watch: false,
      merge_logs: true,
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
  ],
};
