import pandas as pd


class ParameterChecker:
    """
    参数核查器类，用于重构现有的参数核查逻辑
    支持单值参数和多值参数（如开关组）的核查
    """

    def __init__(self, knowledge_file="参数知识库.xlsx", knowledge_sheet="空域配置"):
        """
        初始化参数核查器

        Args:
            knowledge_file (str): 参数知识库Excel文件路径，默认为"参数知识库.xlsx"
            knowledge_sheet (str): Excel工作表名称，默认为"空域配置"
        """
        self.parameter_knowledge = {}
        self.load_parameter_knowledge(knowledge_file, knowledge_sheet)

    def load_parameter_knowledge(self, file_path="参数知识库.xlsx", sheet_name="空域配置"):
        """
        从Excel文件中加载参数知识库

        Args:
            file_path (str): 参数知识库Excel文件路径，默认为"参数知识库.xlsx"
            sheet_name (str): Excel工作表名称，默认为"空域配置"

        Returns:
            bool: 加载成功返回True，失败返回False
        """
        try:
            # 读取Excel文件
            df = pd.read_excel(file_path, sheet_name=sheet_name)

            # 验证必要的列是否存在
            required_columns = ['MO名称', '参数名称', '参数ID', '参数类型', '期望值', '条件表达式']
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                print(f"Excel文件缺少必要的列: {missing_columns}")
                return False

            # 清空现有的参数知识库
            self.parameter_knowledge = {}

            # 按MO名称分组处理
            for mo_name, mo_group in df.groupby('MO名称'):
                if mo_name not in self.parameter_knowledge:
                    self.parameter_knowledge[mo_name] = {
                        "mo_name": mo_name,
                        "mo_description": mo_group.iloc[0].get('MO描述', ''),
                        "scenario": mo_group.iloc[0].get('场景类型', ''),
                        "parameters": {}
                    }

                # 按参数名称分组处理
                for param_name, param_group in mo_group.groupby('参数名称'):
                    param_type = param_group.iloc[0]['参数类型']
                    param_info = {
                        "parameter_id": param_group.iloc[0].get('参数ID', ''),
                        "parameter_name": param_name,
                        "parameter_type": param_type,  # 'single' 或 'multiple'
                        "parameter_description": param_group.iloc[0].get('参数描述', ''),
                        "expected_values": [],  # 存储期望值列表
                        "conditions": [],  # 存储条件列表
                        "switch_descriptions": {}  # 存储开关描述: {开关名称: 描述}
                    }

                    # 收集所有期望值和条件
                    for _, row in param_group.iterrows():
                        # 单值参数只取第一个期望值
                        if param_type == 'single' and len(param_info['expected_values']) == 0:
                            param_info["expected_values"].append(row.get('期望值', ''))
                            # 处理可能的NaN值，确保条件是字符串类型
                            condition_value = row.get('条件表达式', '')
                            if pd.isna(condition_value):
                                condition_value = ''
                            param_info["conditions"].append(str(condition_value).strip())
                            param_info["parameter_description"] = row.get('参数描述', '')
                        # 多值参数处理合并后的期望值格式
                        elif param_type == 'multiple':
                            expected_value_str = row.get('期望值', '')
                            if expected_value_str:
                                # 解析期望值字符串中的开关配置
                                for switch_str in expected_value_str.split('&'):
                                    if ':' in switch_str:
                                        switch_name, expected_state = switch_str.split(':', 1)
                                        switch_name = switch_name.strip()
                                        expected_state = expected_state.strip()

                                        # 记录所有状态的开关
                                        param_info["expected_values"].append({
                                            'switch_name': switch_name,
                                            'expected_state': expected_state
                                        })
                                        # 存储开关描述
                                        param_info["switch_descriptions"][switch_name] = row.get('参数描述', '')

                                # 处理条件表达式
                                condition_value = row.get('条件表达式', '')
                                if pd.isna(condition_value):
                                    condition_value = ''
                                param_info["conditions"].append(str(condition_value).strip())

                    self.parameter_knowledge[mo_name]["parameters"][param_name] = param_info

            print(f"成功从 {file_path} 的 '{sheet_name}' Sheet 加载了参数知识库")
            print(f"包含 {len(self.parameter_knowledge)} 个MO类型")

            return True

        except FileNotFoundError:
            print(f"文件 {file_path} 不存在")
            return False
        except Exception as e:
            print(f"加载参数知识库时发生错误: {e}")
            return False

    def check_single_param(self, groups, mo_name, param_name, sector_id):
        """
        检查单个参数是否符合预期值并记录结果

        Args:
            groups: 包含MO数据的字典
            mo_name: MO名称
            param_name: 参数名称
            sector_id: 小区ID

        Returns:
            pd.DataFrame: 包含错误信息的DataFrame
        """
        """
        检查单个参数是否符合预期值并记录结果

        Args:
            groups: 包含MO数据的字典
            mo_name: MO名称
            param_name: 参数名称
            sector_id: 小区ID

        Returns:
            pd.DataFrame: 包含错误信息的DataFrame
        """
        # ========== 输入参数验证 ==========
        if not groups or mo_name not in groups:
            print(f"SectorId {sector_id}: {mo_name} 数据不存在")
            return pd.DataFrame()

        tmp = groups[mo_name].copy()
        if tmp.empty:
            print(f"SectorId {sector_id}: {mo_name} 数据为空")
            return pd.DataFrame()

        if param_name not in tmp.columns:
            print(f"SectorId {sector_id}: {mo_name} 缺少参数列: {param_name}")
            return pd.DataFrame()

        # ========== 获取参数知识库配置 ==========
        mo_config = self.parameter_knowledge.get(mo_name)
        if not mo_config:
            print(f"警告: SectorId {sector_id} 参数知识库中未找到 {mo_name} 的配置")
            return pd.DataFrame()

        param_info = mo_config.get("parameters", {}).get(param_name)
        if not param_info:
            print(f"警告: SectorId {sector_id} 参数知识库中未找到 {mo_name}.{param_name} 的配置")
            return pd.DataFrame()

        # ========== 参数检查与错误收集 ==========
        valid_mask = pd.Series(True, index=tmp.index)  # 初始化为全部有效
        error_details = []
        mod_commands = []

        # 将参数值转为字符串进行比较
        current_values = tmp[param_name].astype(str)

        # 根据参数类型分派处理
        if len(param_info["expected_values"]) > 1:
            self._process_multi_value_param(tmp, param_info, current_values, valid_mask, error_details, mod_commands,
                                            mo_name, sector_id)
        else:
            self._process_single_value_param(tmp, param_info, current_values, valid_mask, error_details, mod_commands,
                                             mo_name, sector_id)

        # ========== 生成结果 ==========
        result = tmp.copy()
        result['valid'] = valid_mask
        result['mod'] = mod_commands
        result['error_details'] = error_details

        # 只返回无效的行
        invalid_rows = result[~valid_mask].copy()

        if len(invalid_rows) > 0:
            invalid_rows.loc[:, 'message'] = '配置错误'
            print(f"SectorId {sector_id}: {mo_name}.{param_name} 发现 {len(invalid_rows)} 条配置错误")
        else:
            print(f"SectorId {sector_id}: {mo_name}.{param_name} 所有参数配置正确")

        return invalid_rows

    def _evaluate_condition(self, condition, current_params):
        """
        评估条件表达式是否成立（支持多条件逻辑与运算）

        Args:
            condition: 条件表达式，可以是字符串(支持多条件用逗号分隔)或其他类型
            current_params (dict): 当前MO的所有参数值字典

        Returns:
            bool: 所有条件满足返回True，否则返回False
        """
        # 处理非字符串类型的condition
        if not isinstance(condition, str):
            return True

        condition = condition.strip()
        if not condition:
            return True

        try:
            # 支持多条件用逗号分隔（逻辑与关系）
            conditions = [cond.strip() for cond in condition.split(',') if cond.strip()]
            if not conditions:
                return True

            # 所有条件都必须满足
            for cond in conditions:
                if '=' in cond:
                    param_name, expected_value = cond.split('=', 1)
                    param_name = param_name.strip()
                    expected_value = expected_value.strip()
                    current_value = str(current_params.get(param_name, '')).strip()
                    if current_value != expected_value:
                        return False
                # 对于不包含=的条件，视为无效条件，返回False
                else:
                    return False

            return True
        except Exception as e:
            print(f"评估条件表达式错误: {condition}, 错误: {e}")
            return False

    def _process_multi_value_param(self, tmp, param_info, current_values, valid_mask, error_details, mod_commands,
                                   mo_name, sector_id):
        """处理多值参数（如开关组）的检查逻辑"""
        for idx, current_value in current_values.items():
            # 获取当前行的所有参数值
            current_row = tmp.iloc[idx].to_dict()
            # 解析当前值中的开关状态
            switches = self._parse_multi_value(current_value)

            # 检查每个预期的开关值
            error_found = False
            error_params = []
            mod_params = []
            current_switch_str = []

            # 构建当前开关状态字符串
            for switch_name, state in switches.items():
                current_switch_str.append(f"{switch_name}:{state}")
            current_switch_display = '&'.join(current_switch_str)

            # 解析期望值和条件
            # 获取预期开关配置
            expected_switches = []
            conditions = param_info["conditions"]

            # 构建预期开关配置列表
            for expected_config in param_info["expected_values"]:
                expected_switches.append({
                    'switch_name': expected_config['switch_name'],
                    'expected_state': expected_config['expected_state']
                })

            # 评估所有行级条件，筛选符合条件的行
            all_conditions_met = True
            for condition_str in conditions:
                if not self._evaluate_condition(condition_str, current_row):
                    all_conditions_met = False
                    break

            if not all_conditions_met:
                valid_mask[idx] = True  # 条件不满足的行视为有效
                error_details.append({})
                mod_commands.append('')
                continue

            # 检查每个预期的开关配置
            switch_errors = []
            for expected_config in expected_switches:
                switch_name = expected_config['switch_name']
                expected_state = expected_config['expected_state']

                # 查找对应的开关描述
                switch_description = param_info["switch_descriptions"].get(switch_name, '')

                # 检查开关状态
                # 获取当前开关值
                current_switch_value = switches.get(switch_name, '').strip()

                # 检查开关状态是否匹配
                if current_switch_value != expected_state:
                    error_found = True
                    switch_errors.append({
                        'switch_name': switch_name,
                        'switch_description': switch_description,
                        'error_type': 'mismatch',
                        'expected': f'{switch_name}:{expected_state}',
                        'actual': f'{switch_name}:{current_switch_value}'
                    })

                # 构建MOD命令参数（包含所有状态不匹配的开关）
                if current_switch_value != expected_state:
                    mod_params.append(f"{switch_name}={expected_state}")

            # 为参数创建一个统一的错误对象
            if switch_errors:
                error_params.append({
                    "parameter_name": param_info["parameter_name"],
                    "parameter_id": param_info["parameter_id"],
                    "switch_errors": switch_errors,
                    "mo_name": mo_name
                })
                error_found = True

            if error_found:
                valid_mask[idx] = False
                # 构建期望值显示字符串（包含所有预期检查的开关）
                expected_all_switches = [
                    f"{cfg['switch_name']}:{cfg['expected_state']}"
                    for cfg in param_info["expected_values"]
                ]
                expected_switch_display = '&'.join(expected_all_switches)

                # 构建错误详情，显示所有预期检查的开关
                error_details.append({
                    'parameter_name': param_info['parameter_name'],
                    'parameter_id': param_info['parameter_id'],
                    'expected_value': expected_switch_display,
                    'current_value': current_switch_display,
                    'errors': error_params,
                    'mo_name': mo_name,
                    'description': param_info['parameter_description']
                })
                if mod_params:
                    mod_commands.append(f"MOD {mo_name}:{param_info['parameter_id']}={';'.join(mod_params)};")
                else:
                    mod_commands.append('')
            else:
                error_details.append({})
                mod_commands.append('')

    def _process_single_value_param(self, tmp, param_info, current_values, valid_mask, error_details, mod_commands,
                                    mo_name, sector_id):
        """处理单值参数的检查逻辑"""
        # 确定期望值和构建MOD命令
        expected_value = param_info["expected_values"][0] if param_info["expected_values"] else ''
        mod_command = f"MOD {mo_name}:{param_info['parameter_id']}={expected_value};"

        # 遍历所有行检查条件和值
        for idx, row in tmp.iterrows():
            current_row = row.to_dict()
            current_value = current_values[idx]

            # 检查是否满足所有条件
            all_conditions_met = True
            for cond in param_info["conditions"]:
                if not self._evaluate_condition(cond, current_row):
                    all_conditions_met = False
                    break

            if all_conditions_met:
                # 满足所有条件，检查值是否匹配
                if current_value != expected_value:
                    valid_mask[idx] = False
                    error_details.append({
                        "parameter_name": param_info["parameter_name"],
                        "parameter_id": param_info["parameter_id"],
                        "description": param_info["parameter_description"],
                        "expected_value": expected_value,
                        "current_value": current_value,
                        "mo_name": mo_name,
                        "condition": "且".join(param_info["conditions"])  # 合并所有条件
                    })
                    mod_commands.append(mod_command)
                else:
                    error_details.append({})
                    mod_commands.append('')
            else:
                # 不满足条件，不检查值
                error_details.append({})
                mod_commands.append('')

    def _parse_multi_value(self, value_str):
        """
        解析多值参数（如开关组）

        Args:
            value_str (str): 形如"开关1:开&开关2:关"的字符串

        Returns:
            dict: 解析后的键值对，格式为{开关名称: 状态}
        """
        result = {}
        if isinstance(value_str, str):
            # 处理可能的不同分隔符
            separators = ['&', ',', ';']
            for sep in separators:
                if sep in value_str:
                    parts = value_str.split(sep)
                    break
            else:
                parts = [value_str]

            for part in parts:
                if ':' in part:
                    key, val = part.split(':', 1)
                    result[key.strip()] = val.strip()

        return result

    def check_multiple_params(self, groups, mo_name, param_names, sector_id):
        """
        检查多个参数是否符合预期值并记录结果

        Args:
            groups: 包含MO数据的字典
            mo_name: MO名称
            param_names: 参数名称列表
            sector_id: 小区ID

        Returns:
            pd.DataFrame: 包含所有参数错误信息的DataFrame
        """
        all_errors = pd.DataFrame()

        for param_name in param_names:
            errors = self.check_single_param(groups, mo_name, param_name, sector_id)
            all_errors = pd.concat([all_errors, errors], ignore_index=True)

        return all_errors

    def get_common_groups(self, mo_data):
        """
        获取所有MO数据共有的小区ID组
        """

        def get_group_keys(df):
            if len(df) == 0:
                return set()
            return set(df.groupby(['f_site_id', 'f_cell_id']).groups.keys())

        all_groups = [get_group_keys(df) for df in mo_data.values()]
        return set.intersection(*all_groups) if all_groups else set()

    def create_sample_excel(self, file_path="参数知识库.xlsx"):
        """
        创建示例参数知识库Excel文件
        """
        sample_data = [
            # NRDUCELL - 单值参数示例
            {
                'MO名称': 'NRDUCELL',
                'MO描述': 'NR DU小区',
                '场景类型': '空域配置',
                '参数名称': '小区半径(米)',
                '参数ID': 'CellRadius',
                '参数类型': 'single',
                '参数描述': '该参数表示小区半径，满足一定性能条件下小区所能覆盖的最远距离。FDD和SDL小区半径最大100km，TDD小区半径最大60km。',
                '期望值': '8000',
                '条件表达式': ''
            },
            # NRCELLALGOSWITCH - 多值参数示例（合并开关名称和期望值到期望值列）
            {
                'MO名称': 'NRCELLALGOSWITCH',
                'MO描述': 'NR小区算法开关',
                '场景类型': '空域配置',
                '参数名称': '异频切换算法开关',
                '参数ID': 'InterFreqHoSwitch',
                '参数类型': 'multiple',
                '参数描述': '异频切换相关算法开关组，包含基于覆盖、基于SSB SINR等多种切换控制开关',
                '期望值': '基于覆盖的异频切换开关:开',
                '开关描述': '基于覆盖的异频切换控制开关',
                '条件表达式': 'SSB参数1=1,SSB参数2=2'
            },
            {
                'MO名称': 'NRCELLALGOSWITCH',
                'MO描述': 'NR小区算法开关',
                '场景类型': '空域配置',
                '参数名称': '异频切换算法开关',
                '参数ID': 'InterFreqHoSwitch',
                '参数类型': 'multiple',
                '参数描述': '异频切换相关算法开关组，包含基于覆盖、基于SSB SINR等多种切换控制开关',
                '期望值': '异频重定向开关:开',
                '开关描述': '异频重定向功能控制开关',
                '条件表达式': 'SSB参数1=1,SSB参数2=2'
            },
            # NRINTERRATHOPARAM - 带条件的单值参数
            {
                'MO名称': 'NRINTERRATHOPARAM',
                'MO描述': 'NR异频切换参数',
                '场景类型': '空域配置',
                '参数名称': 'CC值',
                '参数ID': 'CCValue',
                '参数类型': 'single',
                '参数描述': '条件依赖参数，根据SSB参数值确定CC值',
                '期望值': 'A',
                '条件表达式': 'SSB参数=2'
            },
            {
                'MO名称': 'NRINTERRATHOPARAM',
                'MO描述': 'NR异频切换参数',
                '场景类型': '空域配置',
                '参数名称': 'CC值',
                '参数ID': 'CCValue',
                '参数类型': 'single',
                '参数描述': '条件依赖参数，根据SSB参数值确定CC值',
                '期望值': 'B',
                '条件表达式': 'SSB参数=3'
            },
            # NRRELATION - 基础单值参数
            {
                'MO名称': 'NRRELATION',
                'MO描述': 'NR邻区关系',
                '场景类型': '空域配置',
                '参数名称': 'SSB参数',
                '参数ID': 'NeighborSSB',
                '参数类型': 'single',
                '参数描述': '邻区的SSB配置（与NRDUCELL的本小区SSB含义不同）',
                '期望值': '5',
                '条件表达式': ''
            }
        ]

        df = pd.DataFrame(sample_data)

        try:
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='空域配置', index=False)

            print(f"示例参数知识库文件已创建: {file_path}")
            return True

        except Exception as e:
            print(f"创建示例文件时发生错误: {e}")
            return False


# 测试代码
if __name__ == '__main__':
    # 创建参数核查器实例
    checker = ParameterChecker()

    # 如果参数知识库不存在，创建示例文件
    if not checker.parameter_knowledge:
        checker.create_sample_excel()
        checker.load_parameter_knowledge()

    # ------------------------------
    # 测试1: 参数知识库加载测试
    # ------------------------------
    print("\n=== 测试1: 参数知识库加载测试 ===")
    print(f"加载的MO类型数量: {len(checker.parameter_knowledge)}")
    assert len(checker.parameter_knowledge) > 0, "参数知识库加载失败"

    # ------------------------------
    # 测试2: 条件表达式评估测试
    # ------------------------------
    print("\n=== 测试2: 条件表达式评估测试 ===")
    test_conditions = [
        ("SSB参数=2", {"SSB参数": "2"}, True),
        ("SSB参数=3", {"SSB参数": "2"}, False),
        ("", {"任意参数": "值"}, True),
        (None, {"参数": "值"}, True),
        (123, {"参数": "值"}, True),
        ("小区半径=8000,异频切换=开", {"小区半径": "8000", "异频切换": "开"}, True)
    ]
    for cond, params, expected in test_conditions:
        result = checker._evaluate_condition(cond, params)
        print(f"条件: {cond!r}, 参数: {params}, 预期: {expected}, 实际: {result}")
        assert result == expected, f"条件测试失败: {cond}"

    # ------------------------------
    # 测试3: 多值参数解析测试
    # ------------------------------
    print("\n=== 测试3: 多值参数解析测试 ===")
    test_values = [
        ("基于覆盖的异频切换开关:开&异频重定向开关:开", {"基于覆盖的异频切换开关": "开", "异频重定向开关": "开"}),
        ("开关1:关,开关2:开", {"开关1": "关", "开关2": "开"}),
        ("单一开关:开", {"单一开关": "开"}),
        ("无效格式", {})
    ]
    for value_str, expected in test_values:
        result = checker._parse_multi_value(value_str)
        print(f"输入: {value_str!r}, 预期: {expected}, 实际: {result}")
        assert result == expected, f"多值参数解析失败: {value_str}"

    # ------------------------------
    # 测试4: 单参数检查测试
    # ------------------------------
    print("\n=== 测试4: 单参数检查测试 ===")
    test_data_single = {
        'NRDUCELL': pd.DataFrame([
            {'f_site_id': '13566583', 'f_cell_id': '4', '小区半径(米)': '4000'},
            {'f_site_id': '13566583', 'f_cell_id': '5', '小区半径(米)': '8000'}
        ])
    }
    errors = checker.check_single_param(test_data_single, 'NRDUCELL', '小区半径(米)', 'TEST_SECTOR_1')
    print(f"发现{len(errors)}个错误配置")
    assert len(errors) == 1, "单参数检查结果不符合预期"

    # ------------------------------
    # 测试5: 多参数检查测试
    # ------------------------------
    print("\n=== 测试5: 多参数检查测试 ===")
    test_data_multi = {
        'NRDUCELL': pd.DataFrame([{'f_site_id': '13566583', 'f_cell_id': '4', '小区半径(米)': '4000'}]),
        'NRCELLALGOSWITCH': pd.DataFrame(
            [{'f_site_id': '13566583', 'f_cell_id': '4', 'SSB参数1': '1', 'SSB参数2': '2',
              '异频切换算法开关': '基于覆盖的异频切换开关:关&异频重定向开关:关&基于SSB SINR的异频切换开关:关'}])
    }
    multi_errors = checker.check_multiple_params(test_data_multi, 'NRCELLALGOSWITCH', ['异频切换算法开关'],
                                                 'TEST_SECTOR_2')
    # multi_errors = checker.check_multiple_params(test_data_multi, 'NRDUCELL', ['小区半径(米)'], 'TEST_SECTOR_2')
    print(f"多参数检查发现{len(multi_errors)}个错误")
    assert len(multi_errors) == 1, "多参数检查结果不符合预期"

    # ------------------------------
    # 测试6: 多值参数检查测试
    # ------------------------------
    print("\n=== 测试6: 多值参数检查测试 ===")
    test_data_multi_value = {
        'NRCELLALGOSWITCH': pd.DataFrame([
            {
                'f_site_id': '13566583',
                'f_cell_id': '4',
                'SSB参数1': '1',
                'SSB参数2': '2',
                '异频切换算法开关': '基于覆盖的异频切换开关:关&异频重定向开关:开'
            }
        ])
    }
    switch_errors = checker.check_single_param(test_data_multi_value, 'NRCELLALGOSWITCH', '异频切换算法开关',
                                               'TEST_SECTOR_3')
    print(f"多值参数检查发现{len(switch_errors)}个错误")
    assert len(switch_errors) == 1, "多值参数检查结果不符合预期"

    # ------------------------------
    # 测试7: 条件参数检查测试
    # ------------------------------
    print("\n=== 测试7: 条件参数检查测试 ===")
    test_data_conditional = {
        'NRINTERRATHOPARAM': pd.DataFrame([
            {
                'f_site_id': '13566583',
                'f_cell_id': '4',
                'SSB参数': '2',
                'CC值': 'B'  # 当SSB参数=2时，CC值应为A
            },
            {
                'f_site_id': '13566583',
                'f_cell_id': '5',
                'SSB参数': '3',
                'CC值': 'B'  # 当SSB参数=3时，CC值应为B
            }
        ])
    }
    conditional_errors = checker.check_single_param(test_data_conditional, 'NRINTERRATHOPARAM', 'CC值', 'TEST_SECTOR_4')
    print(f"条件参数检查发现{len(conditional_errors)}个错误")
    assert len(conditional_errors) == 1, "条件参数检查结果不符合预期"

    # ------------------------------
    # 测试8: 错误处理测试
    # ------------------------------
    print("\n=== 测试8: 错误处理测试 ===")
    test_data_error = {
        'INVALID_MO': pd.DataFrame([{'f_site_id': '1', 'f_cell_id': '1', '参数': '值'}])
    }
    empty_result = checker.check_single_param(test_data_error, 'INVALID_MO', '参数', 'TEST_SECTOR_5')
    print(f"无效MO测试返回{len(empty_result)}条结果")
    assert len(empty_result) == 0, "错误处理测试失败"

    print("\n所有测试通过！")