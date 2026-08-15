"""启动脚本：uvicorn 运行量化交易系统后端。"""
import uvicorn
from app import main

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
