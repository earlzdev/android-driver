package com.earldev.flakydemo.core

data class Review(
    val author: String,
    val stars: Int,
    val body: String,
)

data class Item(
    val id: Int,
    val name: String,
    val price: Int,
    val category: String,
    val inStock: Boolean,
    val onSale: Boolean,
    val reviews: List<Review>,
)

private val ADJECTIVES = listOf(
    "Copper", "Basalt", "Ivory", "Cobalt", "Amber", "Slate", "Cedar", "Onyx", "Linen", "Quartz",
)

private val NOUNS = listOf(
    "Lamp", "Kettle", "Mixer", "Chair", "Clock", "Shelf",
)

val CATEGORIES = listOf("Kitchen", "Lighting", "Seating", "Storage")

/** Deterministic catalog: the same 60 rows on every launch, so a repro can name a row by id. */
fun buildCatalog(): List<Item> = (1..60).map { id ->
    val name = "${ADJECTIVES[id % ADJECTIVES.size]} ${NOUNS[id % NOUNS.size]} ${100 + id}"
    // BUG-CAT-04 companion: ids 13 and 42 ship with no reviews at all, which the detail screen's
    // Reviews tab does not guard against.
    val reviewCount = if (id == 13 || id == 42) 0 else (id % 4) + 1
    Item(
        id = id,
        name = name,
        price = 400 + (id * 137) % 9600,
        category = CATEGORIES[id % CATEGORIES.size],
        inStock = id % 7 != 0,
        onSale = id % 5 == 0,
        reviews = (1..reviewCount).map { n ->
            Review(
                author = "reviewer_${id}_$n",
                stars = 1 + (id + n) % 5,
                body = "Held up for ${(id * n) % 30 + 1} weeks of daily use.",
            )
        },
    )
}

fun formatPrice(cents: Int): String = "$" + (cents / 100) + "." + (cents % 100).toString().padStart(2, '0')
