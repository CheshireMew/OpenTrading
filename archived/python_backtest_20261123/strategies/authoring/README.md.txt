# 策略作者源码

此目录是策略的维护入口。templates/*.py.in 保存版本差异，shared/*.inc 保存相同的参数定义、云带计算、入场和观察记录片段。模板中的 @@include:名称@@ 在生成时替换为对应片段的原始字节。

在项目根目录运行：

    node scripts/run_backend_python.mjs -m scripts.generate_strategies --check
    node scripts/run_backend_python.mjs -m scripts.generate_strategies --write

前一条只检查，后一条恢复缺失或变化的生成文件。策略目录顶层的 24 个 Python 文件是独立输出，不需要在运行时导入作者模板；现有单文件快照和哈希复现方式保持不变。

manifest.json 记录历史版本的输出哈希。旧版本生成结果必须逐字节一致，不能通过更新旧哈希来隐藏行为变化。修改算法应建立新策略版本：复制对应模板到新版本名、修改其元数据与差异、登记新版本的模板及输出哈希，再生成独立文件。若修改共享片段会影响旧版本，应新增片段供新版本引用，保留旧版本引用的内容。

连续匹配的作者片段有时包括函数之间的边界；它们是生成模板，不作为 Python 模块导入。生成器会对最终文件做语法和哈希检查，自动化测试还会核对顶层策略均已登记。
