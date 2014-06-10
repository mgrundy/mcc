#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "list.h"

/* This file consists of functions designed to manipulate
 * a linked list structure. The linked list consists of a
 * struct List, which keeps track of the first and last
 * elements of the list. Elements of the list are represented
 * by struct Node. A node consists of a pointer to the next
 * node, and pointers to the key, value, and type of the value
 * stored by the node. This linked list is designed to output
 * its data in the form of a JSON object.
 */

static void die (const char *message) {
    perror(message);
    exit(1);
}

void initList (struct List *list) {
    list->front = NULL;
    list->back = NULL;
}

int isEmptyList (struct List *list) {
    return list->front == NULL;
}

/* Add key/value entry to list. type represents the type of the 
 * value.
 */
void addToList (struct List *list, const char *key, const void *value,
                const char *type) {
    struct Node *newNode = (struct Node *) malloc(sizeof(struct Node));
    if (newNode == NULL) {
        die("malloc failed");
    }
   
    if (isEmptyList(list)) {
        list->front = newNode; 
        list->back = newNode;
    }

    else {
        list->back->next = newNode;
        list->back = newNode;
    }

    newNode->type = (char *) type;
    newNode->next = NULL;
    
    // Make copies of the key and value arguments
    newNode->key = (char *) malloc(strlen(key) + 1);
    if (newNode->key == NULL) {
        die("malloc failed");
    }
    strcpy(newNode->key, key);

    if (strcmp(newNode->type, "int") == 0) {
        newNode->value = malloc(sizeof(long));
        *((long *) newNode->value) = *(long *)value;
    }

    if (strcmp(newNode->type, "string") == 0) {
        newNode->value = malloc(strlen((char *) value) + 1);
        strcpy((char *) newNode->value, (char *) value);
    }

    /* Note that adding a node with data type "list" will
     * only work if the list to be added is in its final form
     * prior to adding. The copy of the list generated by 
     * addToList will reflect the data that was present in the
     * source list at the time of the copy.
     */
    if (strcmp(newNode->type, "list") == 0) {
        newNode->value = malloc(sizeof(struct List));
        struct List *newNodeList = (struct List *) newNode->value;
        struct List *argList = (struct List *) value;
        newNodeList->front = argList->front;
        newNodeList->back = argList->back;
    }

    if (strcmp(newNode->type, "char") == 0) {
        newNode->value = (char *) malloc(sizeof(char));
        *((char *) newNode->value) = *(char *)value;
    }

    if (newNode->value == NULL) {
        die("malloc failed");
    }

}

/* Helper function for printing the data in a struct List. Prints
 * data in the Node and then frees data and Node.
 */
static void printAndDeleteNode (struct Node *node, FILE *file) {
    int proceed = 1;
    struct Node *next = node->next;
    
    // Determine whether to proceed to next recursive call.
    if (next == NULL) {
        proceed = 0;
    }
   
    // If node has List as its value, recursively print list. 
    // Only print list if list is not empty.
    if (strcmp(node->type, "list") == 0 && 
        !isEmptyList((struct List *) node->value)) {

        fprintf(file, "%s: [", node->key);
        printList((struct List *) node->value, file);
        fprintf(file, "]");
    }
    
    if (strcmp(node->type, "int") == 0) {
       fprintf(file, "%s: %lu", node->key, *(long *) node->value);
    }

    if (strcmp(node->type, "string") == 0) {
        fprintf(file, "%s: %s", node->key, (char *) node->value);
    }

    if (strcmp(node->type, "char") == 0) {
        fprintf(file, "%s: %c", node->key, *(char *) node->value);
    }

    // Done printing current node, free allocated data.
    free(node->key);
    free(node->value);
    free(node);

    if (proceed) {
        // Don't print a comma if next node data is an empty list.
        if (strcmp(next->type, "list") != 0 || 
            !isEmptyList((struct List *) next->value)) {
            fprintf(file, ", ");
        }

        printAndDeleteNode(next, file);
    }
}

/* Helper function for printing the elements in a list.
 */
void printList (struct List *list, FILE *file) {
    printAndDeleteNode (list->front, file);
}

/* Print elements in a list as a JSON object.
 */
void printDocument (struct List *list, FILE *file) {
    fprintf(file, "\n{");
    printList(list, file);
    fprintf(file, "}\n");
    fflush(file);
}

