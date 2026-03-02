"""
数据加载模块

提供对本地历史数据文件（CSV/Excel/DB）的加载逻辑。

设计原则：
1. 支持多种本地数据格式
2. 自动推断数据类型
3. 使用 @error_handler 装饰器
"""

import logging
from pathlib import Path
from typing import List, Optional, Union

import pandas as pd

logger = logging.getLogger(__name__)


def _setup_error_handler():
    """设置错误处理装饰器"""
    try:
        from src.utils.error_handler import error_handler
        return error_handler
    except ImportError:
        def error_handler_decorator(**kwargs):
            def decorator(func):
                return func
            return decorator
        return error_handler_decorator

error_handler = _setup_error_handler()


class DataLoader:
    """
    本地数据加载器
    
    支持格式：
    - CSV
    - Excel (.xlsx, .xls)
    - Parquet
    - JSON
    """

    def __init__(self, base_path: Optional[str] = None):
        """
        初始化加载器
        
        Args:
            base_path: 基础路径，默认当前目录
        """
        self.base_path = Path(base_path) if base_path else Path.cwd()
        logger.info(f"DataLoader initialized with base_path: {self.base_path}")

    @error_handler(logger=logger, reraise=False, default_return=pd.DataFrame())
    def load_csv(
        self,
        file_path: Union[str, Path],
        parse_dates: bool = True,
        index_col: Optional[str] = "timestamp",
        **kwargs
    ) -> pd.DataFrame:
        """
        加载 CSV 文件
        
        Args:
            file_path: 文件路径
            parse_dates: 是否解析日期
            index_col: 索引列名
            **kwargs: pandas read_csv 其他参数
            
        Returns:
            DataFrame
        """
        full_path = self._resolve_path(file_path)

        logger.info(f"Loading CSV: {full_path}")

        df = pd.read_csv(
            full_path,
            parse_dates=parse_dates,
            index_col=index_col if parse_dates else None,
            **kwargs
        )

        logger.info(f"Loaded {len(df)} rows from {full_path.name}")
        return df

    @error_handler(logger=logger, reraise=False, default_return=pd.DataFrame())
    def load_excel(
        self,
        file_path: Union[str, Path],
        sheet_name: Union[str, int] = 0,
        parse_dates: bool = True,
        index_col: Optional[str] = "timestamp",
        **kwargs
    ) -> pd.DataFrame:
        """
        加载 Excel 文件
        
        Args:
            file_path: 文件路径
            sheet_name: 工作表名称或索引
            parse_dates: 是否解析日期
            index_col: 索引列名
            **kwargs: pandas read_excel 其他参数
            
        Returns:
            DataFrame
        """
        full_path = self._resolve_path(file_path)

        logger.info(f"Loading Excel: {full_path}, sheet: {sheet_name}")

        df = pd.read_excel(
            full_path,
            sheet_name=sheet_name,
            parse_dates=parse_dates,
            index_col=index_col if parse_dates else None,
            **kwargs
        )

        logger.info(f"Loaded {len(df)} rows from {full_path.name}")
        return df

    @error_handler(logger=logger, reraise=False, default_return=pd.DataFrame())
    def load_parquet(
        self,
        file_path: Union[str, Path],
        **kwargs
    ) -> pd.DataFrame:
        """
        加载 Parquet 文件
        
        Args:
            file_path: 文件路径
            **kwargs: pandas read_parquet 其他参数
            
        Returns:
            DataFrame
        """
        full_path = self._resolve_path(file_path)

        logger.info(f"Loading Parquet: {full_path}")

        df = pd.read_parquet(full_path, **kwargs)

        logger.info(f"Loaded {len(df)} rows from {full_path.name}")
        return df

    @error_handler(logger=logger, reraise=False, default_return=pd.DataFrame())
    def load_json(
        self,
        file_path: Union[str, Path],
        parse_dates: bool = True,
        **kwargs
    ) -> pd.DataFrame:
        """
        加载 JSON 文件
        
        Args:
            file_path: 文件路径
            parse_dates: 是否解析日期
            **kwargs: pandas read_json 其他参数
            
        Returns:
            DataFrame
        """
        full_path = self._resolve_path(file_path)

        logger.info(f"Loading JSON: {full_path}")

        df = pd.read_json(full_path, parse_dates=parse_dates, **kwargs)

        logger.info(f"Loaded {len(df)} rows from {full_path.name}")
        return df

    @error_handler(logger=logger, reraise=False, default_return=pd.DataFrame())
    def load_auto(
        self,
        file_path: Union[str, Path],
        **kwargs
    ) -> pd.DataFrame:
        """
        自动识别格式并加载
        
        Args:
            file_path: 文件路径
            **kwargs: 其他参数
            
        Returns:
            DataFrame
        """
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix == ".csv":
            return self.load_csv(file_path, **kwargs)
        if suffix in [".xlsx", ".xls"]:
            return self.load_excel(file_path, **kwargs)
        if suffix == ".parquet":
            return self.load_parquet(file_path, **kwargs)
        if suffix == ".json":
            return self.load_json(file_path, **kwargs)
        logger.warning(f"Unknown file format: {suffix}, trying CSV")
        return self.load_csv(file_path, **kwargs)

    def _resolve_path(self, file_path: Union[str, Path]) -> Path:
        """解析文件路径"""
        path = Path(file_path)
        if not path.is_absolute():
            path = self.base_path / path
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return path

    @error_handler(logger=logger, reraise=False, default_return=[])
    def list_data_files(
        self,
        directory: Optional[str] = None,
        extensions: Optional[List[str]] = None
    ) -> List[Path]:
        """
        列出目录中的数据文件
        
        Args:
            directory: 目录路径
            extensions: 文件扩展名列表
            
        Returns:
            文件路径列表
        """
        if extensions is None:
            extensions = [".csv", ".xlsx", ".xls", ".parquet", ".json"]

        dir_path = self._resolve_path(directory) if directory else self.base_path

        if not dir_path.is_dir():
            logger.warning(f"Not a directory: {dir_path}")
            return []

        files = []
        for ext in extensions:
            files.extend(dir_path.glob(f"*{ext}"))

        logger.info(f"Found {len(files)} data files in {dir_path}")
        return sorted(files)


class MarketDataLoader(DataLoader):
    """
    市场数据加载器 - 专门用于加载 OHLCV 数据
    
    扩展功能：
    1. 自动验证 OHLCV 结构
    2. 时间索引标准化
    3. 多文件批量加载
    """

    REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]

    @error_handler(logger=logger, reraise=False, default_return=pd.DataFrame())
    def load_market_data(
        self,
        file_path: Union[str, Path],
        **kwargs
    ) -> pd.DataFrame:
        """
        加载市场数据（OHLCV）
        
        Args:
            file_path: 文件路径
            **kwargs: 父类加载参数
            
        Returns:
            OHLCV DataFrame
        """
        df = self.load_auto(file_path, **kwargs)

        # 标准化列名
        df = self._normalize_columns(df)

        # 验证结构
        if not self._validate_ohlcv(df):
            logger.warning(f"Invalid OHLCV structure in {file_path}")

        return df

    @error_handler(logger=logger, reraise=False, default_return=pd.DataFrame())
    def load_multiple(
        self,
        file_paths: List[Union[str, Path]],
        symbol_column: Optional[str] = None,
        **kwargs
    ) -> pd.DataFrame:
        """
        批量加载多个文件
        
        Args:
            file_paths: 文件路径列表
            symbol_column: 币种标识列名
            **kwargs: 加载参数
            
        Returns:
            合并后的 DataFrame
        """
        dfs = []

        for path in file_paths:
            try:
                df = self.load_market_data(path, **kwargs)
                if symbol_column and symbol_column not in df.columns:
                    # 从文件名提取币种
                    df[symbol_column] = Path(path).stem.split("_")[0]
                dfs.append(df)
            except Exception as e:
                logger.error(f"Failed to load {path}: {e}")

        if not dfs:
            return pd.DataFrame()

        result = pd.concat(dfs, ignore_index=True)
        logger.info(f"Loaded {len(result)} rows from {len(dfs)} files")

        return result

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化列名"""
        result = df.copy()

        # 列名映射
        column_map = {
            "open": "open",
            "Open": "open",
            "OPEN": "open",
            "high": "high",
            "High": "high",
            "HIGH": "high",
            "low": "low",
            "Low": "low",
            "LOW": "low",
            "close": "close",
            "Close": "close",
            "CLOSE": "close",
            "volume": "volume",
            "Volume": "volume",
            "VOLUME": "volume",
            "vol": "volume",
            "Vol": "volume",
        }

        result = result.rename(columns=column_map)

        return result

    def _validate_ohlcv(self, df: pd.DataFrame) -> bool:
        """验证 OHLCV 结构"""
        for col in self.REQUIRED_COLUMNS:
            if col not in df.columns:
                return False

        return True


__all__ = ["DataLoader", "MarketDataLoader"]
