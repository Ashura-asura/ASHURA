# Trait (computer programming)

In computer programming, a trait is a language concept that represents a set of methods that can be used to extend the functionality of a class.

== Rationale ==
In object-oriented programming, behavior is sometimes shared between classes which are not related to each other. For example, many unrelated classes may have methods to serialize objects to JSON. Historically, there have been several approaches to solve this without duplicating the code in every class needing the behavior. Other approaches include multiple inheritance and mixins, but these have drawbacks: the behavior of the code may unexpectedly change if the order in which the mixins are applied is altered, or if new methods are added to the parent classes or mixins.
Traits solve these problems by allowing classes to use the trait and get the desired behavior. If a class uses more than one trait, the order in which the traits are used does not matter. The methods provided by the traits have direct access to the data of the class.

== Characteristics ==
Traits combine aspects of protocols (interfaces) and mixins. Like an interface, a trait defines one or more method signatures, of which implementing classes must provide implementations...
