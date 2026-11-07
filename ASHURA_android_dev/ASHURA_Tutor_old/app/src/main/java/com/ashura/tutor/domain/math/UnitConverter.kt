package com.ashura.tutor.domain.math

import java.math.BigDecimal
import java.math.MathContext
import java.math.RoundingMode

/** Deterministic unit conversion for common school units (spec §11.2, unit/dimension checks). */
object UnitConverter {

    data class Request(val value: BigDecimal, val from: String, val to: String)
    sealed interface Result {
        data class Ok(val text: String) : Result
        data class Error(val message: String) : Result
    }

    private enum class Dim { LENGTH, MASS, TIME, VOLUME, SPEED, TEMPERATURE }
    private data class Unit(val dim: Dim, val factor: BigDecimal)

    private val MC = MathContext(15, RoundingMode.HALF_EVEN)

    private fun u(dim: Dim, f: String) = Unit(dim, BigDecimal(f))

    private val units: Map<String, Unit> = buildMap {
        fun add(d: Dim, f: String, vararg names: String) = names.forEach { put(it, u(d, f)) }
        add(Dim.LENGTH, "0.001", "mm", "millimeter", "millimeters", "millimetre", "millimetres")
        add(Dim.LENGTH, "0.01", "cm", "centimeter", "centimeters", "centimetre", "centimetres")
        add(Dim.LENGTH, "1", "m", "meter", "meters", "metre", "metres")
        add(Dim.LENGTH, "1000", "km", "kilometer", "kilometers", "kilometre", "kilometres")
        add(Dim.LENGTH, "0.0254", "in", "inch", "inches")
        add(Dim.LENGTH, "0.3048", "ft", "foot", "feet")
        add(Dim.LENGTH, "0.9144", "yd", "yard", "yards")
        add(Dim.LENGTH, "1609.344", "mi", "mile", "miles")
        add(Dim.MASS, "0.000001", "mg", "milligram", "milligrams")
        add(Dim.MASS, "0.001", "g", "gram", "grams")
        add(Dim.MASS, "1", "kg", "kilogram", "kilograms")
        add(Dim.MASS, "1000", "t", "tonne", "tonnes")
        add(Dim.MASS, "0.028349523125", "oz", "ounce", "ounces")
        add(Dim.MASS, "0.45359237", "lb", "lbs", "pound", "pounds")
        add(Dim.TIME, "0.001", "ms")
        add(Dim.TIME, "1", "s", "sec", "second", "seconds")
        add(Dim.TIME, "60", "min", "minute", "minutes")
        add(Dim.TIME, "3600", "h", "hr", "hour", "hours")
        add(Dim.TIME, "86400", "day", "days")
        add(Dim.VOLUME, "0.001", "ml", "milliliter", "milliliters", "millilitre", "millilitres")
        add(Dim.VOLUME, "1", "l", "liter", "liters", "litre", "litres")
        add(Dim.VOLUME, "3.785411784", "gal", "gallon", "gallons") // US gallon
        add(Dim.SPEED, "1", "m/s")
        add(Dim.SPEED, "0.2777777777777778", "km/h", "kph")
        add(Dim.SPEED, "0.44704", "mph")
        for (t in listOf("c", "°c", "celsius", "f", "°f", "fahrenheit", "k", "kelvin")) put(t, u(Dim.TEMPERATURE, "1"))
    }

    private val pattern = Regex(
        "^(?:convert\\s+)?(-?\\d+(?:\\.\\d+)?)\\s*([a-z°/]+)\\s+(?:to|in|into)\\s+([a-z°/]+)\\s*[?.]?$"
    )

    /** Parses "convert 5 km to m" / "5 km in m"; null unless both units are known. */
    fun parse(text: String): Request? {
        if (text.length > 120) return null // bounded work on arbitrary user input
        val m = pattern.matchEntire(DigitNormalizer.toAscii(text).trim().lowercase()) ?: return null
        val from = m.groupValues[2]; val to = m.groupValues[3]
        if (from !in units || to !in units) return null
        return Request(BigDecimal(m.groupValues[1]), from, to)
    }

    fun convert(req: Request): Result {
        val a = units[req.from]!!; val b = units[req.to]!!
        if (a.dim != b.dim) return Result.Error("Cannot convert ${req.from} to ${req.to}: different kinds of quantity (${a.dim.name.lowercase()} vs ${b.dim.name.lowercase()}).")
        val out = if (a.dim == Dim.TEMPERATURE) convertTemperature(req.value, tempKind(req.from), tempKind(req.to))
        else req.value.multiply(a.factor, MC).divide(b.factor, MC)
        if (a.dim == Dim.TEMPERATURE && tempKind(req.from) == 'k' && req.value.signum() < 0)
            return Result.Error("Kelvin cannot be negative.")
        val shown = out.round(MathContext(10, RoundingMode.HALF_EVEN)).stripTrailingZeros()
            .let { if (it.signum() == 0) BigDecimal.ZERO else it }.toPlainString()
        val input = req.value.stripTrailingZeros().toPlainString()
        return Result.Ok("$input ${req.from} = $shown ${req.to}")
    }

    private fun tempKind(name: String): Char = when (name) {
        "c", "°c", "celsius" -> 'c'; "f", "°f", "fahrenheit" -> 'f'; else -> 'k'
    }

    private fun convertTemperature(v: BigDecimal, from: Char, to: Char): BigDecimal {
        val c = when (from) {
            'c' -> v
            'f' -> v.subtract(BigDecimal(32)).multiply(BigDecimal(5), MC).divide(BigDecimal(9), MC)
            else -> v.subtract(BigDecimal("273.15"))
        }
        return when (to) {
            'c' -> c
            'f' -> c.multiply(BigDecimal(9), MC).divide(BigDecimal(5), MC).add(BigDecimal(32))
            else -> c.add(BigDecimal("273.15"))
        }
    }
}
