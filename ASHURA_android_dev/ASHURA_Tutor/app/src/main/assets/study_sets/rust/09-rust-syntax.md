# Rust syntax

The syntax of Rust is the set of rules defining how a Rust program is written and compiled.
Rust's syntax is similar to that of C and C++, although many of its features were influenced by functional programming languages such as OCaml.

== Basics ==
Although Rust syntax is heavily influenced by the syntaxes of C and C++, the syntax of Rust is far more distinct from C++ syntax than Java or C#, as those languages have more C-style declarations, primitive names, and keywords.
Below is a "Hello, World!" program in Rust. The fn keyword denotes a function, and the println! macro (see § Macros) prints the message to standard output. Statements in Rust are separated by semicolons.

=== Reserved words ===

==== Keywords ====
The following 42 words are reserved, and may not be used as identifiers.

==== Unused words ====
The following words are reserved as keywords, but currently have no use or purpose. There are 14 unused words.

=== Variables ===
Variables in Rust are defined through the let keyword. The example below assigns a value to the variable with name foo and outputs its value.

Variables are immutable by default, but adding the mut keyword allows the variable to be mutated. The following example uses...
