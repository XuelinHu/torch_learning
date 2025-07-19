# ollama_search_agent.py

from langchain_community.chat_models import ChatOllama
from langchain_community.tools import DuckDuckGoSearchRun
from langchain.prompts import ChatPromptTemplate
from langchain.chains import LLMChain
from langchain_core.output_parsers import StrOutputParser


# 1. 初始化模型和搜索工具

ollama = ChatOllama(
    model="deepseek-r1:8b",
    base_url="http://192.168.1.8:11434"  # 修改为你的实际 IP 和端口
)
search_tool = DuckDuckGoSearchRun()

# 2. 定义通用的 prompt 和 chain
prompt = ChatPromptTemplate.from_template("请简洁准确地回答这个问题：{question}")
llm_chain = prompt | ollama | StrOutputParser()

# 3. 回答是否失败的判断函数
def should_use_search(response: str) -> bool:
    fail_keywords = ["不知道", "无法回答", "我不确定", "查不到", "不能回答", "没有相关信息"]
    return any(k in response.lower() for k in fail_keywords)


# 4. 主逻辑函数
def ask_question(question: str) -> str:
    print(f"🧠 使用 Ollama 回答问题：{question}")
    response = llm_chain.invoke({"question": question})
    print(f"🔍 Ollama 回答结果：{response}\n")

    if should_use_search(response):
        print("⚠️ Ollama 无法有效回答，改用 DuckDuckGo 搜索...\n")
        search_result = search_tool.run(question)
        print(f"🌐 DuckDuckGo 搜索结果：{search_result}\n")

        follow_up_prompt = ChatPromptTemplate.from_template(
            "根据以下搜索内容，准确简洁地回答这个问题：\n搜索内容：{search_result}\n问题：{question}"
        )
        follow_up_chain = follow_up_prompt | ollama | StrOutputParser()

        final_answer = follow_up_chain.invoke({
            "search_result": search_result,
            "question": question
        })
        return f"📘 综合搜索后回答：{final_answer}"
    else:
        return f"✅ Ollama 回答：{response}"


# 5. 测试入口（可运行）
if __name__ == "__main__":
    while True:
        user_input = input("\n❓请输入你的问题（输入 'exit' 退出）：\n> ")
        if user_input.lower() in ["exit", "quit"]:
            break
        result = ask_question(user_input)
        print(f"\n📝 最终回答：\n{result}")
