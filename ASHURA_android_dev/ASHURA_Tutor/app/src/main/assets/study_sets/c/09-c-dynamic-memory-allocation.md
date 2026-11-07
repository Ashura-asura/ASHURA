# C dynamic memory allocation

C dynamic memory allocation refers to performing manual memory management for dynamic memory allocation in the C programming language via a group of functions in the C standard library, mainly malloc, realloc, calloc, aligned_alloc and free.
The C++ programming language includes these functions; however, the operators new and delete provide similar functionality and are recommended by that language's authors. Still, there are several situations in which using new/delete is not applicable, such as garbage collection code or performance-sensitive code, and a combination of malloc and new may be required instead of the higher-level new operator.
Many different implementations of the actual memory allocation mechanism, used by malloc, are available. Their performance varies in both execution time and required memory.
