from time import perf_counter
from datetime import timedelta

#---------------------------------------------------------------------------
#                              CLASS
#---------------------------------------------------------------------------
class Timer:
    """
    Class for measuring code execution time
    """
    _tic = None
    _toc = 0.0
    
    def __init__(self, name=None):
        self._name = name

    def __enter__(self):
        self._start = perf_counter()
        self._tic = self._start
        
        return self

    def __exit__(self, type, value, traceback):
        if self._name:
            print(f"[TIMER: {self._name}] ", end="")
        print(f"Elapsed: {perf_counter() - self._start:<010.3f} seconds")
        
    def tic(self) -> None:
        """
        Sets the time to measure from
        """
        self._tic = perf_counter()
        
    def toc(self) -> float:
        """
        Many toc() functions can be called for one tic()
        If tic() has not been called before, returns 0.0
        
        Returns:
            time elapsed since last tic() called
        """
        if self._tic is not None:
            self._toc = perf_counter() - self._tic
            return self._toc
        else:
            return self._toc
        
    def get_last_toc(self) -> float:
        """
        If tic() or toc() has not been called before, returns 0.0
        
        Returns:
            _type_: _description_
        """
        return self._toc
    
    @staticmethod
    def sec_to_timedelta(seconds: float) -> timedelta:
        return timedelta(seconds=seconds)

        