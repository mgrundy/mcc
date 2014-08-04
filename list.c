/*
 *    Copyright (C) 2014 MongoDB Inc.
 *
 *    This program is free software: you can redistribute it and/or  modify
 *    it under the terms of the GNU Affero General Public License, version 3,
 *    as published by the Free Software Foundation.
 *
 *    This program is distributed in the hope that it will be useful,
 *    but WITHOUT ANY WARRANTY; without even the implied warranty of
 *    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *    GNU Affero General Public License for more details.
 *
 *    You should have received a copy of the GNU Affero General Public License
 *    along with this program.  If not, see <http://www.gnu.org/licenses/>.
 *
 *    As a special exception, the copyright holders give permission to link the
 *    code of portions of this program with the OpenSSL library under certain
 *    conditions as described in each individual source file and distribute
 *    linked combinations including the program with the OpenSSL library. You
 *    must comply with the GNU Affero General Public License in all respects for
 *    all of the code used other than as permitted herein. If you modify file(s)
 *    with this exception, you may extend this exception to your version of the
 *    file(s), but you are not obligated to do so. If you do not wish to do so,
 *    delete this exception statement from your version. If you delete this
 *    exception statement from all source files in the program, then also delete
 *    it in the license file.
 */

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

/* Print relevant error message and exit program.*/
static void die (const char *message) {
    perror(message);
    exit(1);
}

/* Initialize list.*/
void initList (struct List *list) {
    list->front = NULL;
    list->back = NULL;
}

/* Return whether list has nodes.*/
int isEmptyList (const struct List *list) {
    return list->front == NULL;
}

/* Determine whether list or its sublists,
 * if present, has an empty list as its 
 * data value, or is an empty list itself. 
 * Used to prevent printing trailing commas.
 */
static int isEmptyListChain(const struct List *list) {
    if (!isEmptyList(list)) {
        if (list->front->value != NULL) {
           if (strcmp(list->front->type, "array") == 0 || 
               strcmp(list->front->type, "object") == 0) 
               return isEmptyListChain((struct List *) list->front->value);
           else
               return 0;
        }
        else
            return 1;
    }

    return 1;
}

/* Add key/value entry to list. type represents the type of the 
 * value.
 */
void addToList (struct List *list, const char *key, const void *value,
                const char *type) {
    if ((strcmp(type, "array") == 0 ||
         strcmp(type, "object") == 0) && 
        isEmptyListChain((const struct List *) value))
        return;

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

    newNode->type = type;
    newNode->next = NULL;
    
    // Make copies of the key and value arguments
    newNode->key = (char *) malloc(strlen(key) + 3);
    if (newNode->key == NULL) {
        die("malloc failed");
    }
    strcpy(newNode->key, "\"");
    strcpy(newNode->key + 1, key);
    strcpy(newNode->key + strlen(key) + 1, "\"");

    if (strcmp(newNode->type, "long") == 0) {
        newNode->value = malloc(sizeof(long));
        *((long *) newNode->value) = *(const long *)value;
    }

    if (strcmp(newNode->type, "string") == 0) {
        newNode->value = malloc(strlen((const char *) value) + 3);
        strcpy((char *) newNode->value, "\"");
        strcpy((char *) newNode->value + 1, (const char *) value);
        size_t len = strlen((const char *) value);
        strcpy((char *) newNode->value + len + 1, "\"");
    }

    /* Note that adding a node with data type "array" will
     * only work if the list to be added is in its final form
     * prior to adding. The copy of the list generated by 
     * addToList will reflect the data that was present in the
     * source list at the time of the copy.
     * Lists and objects are stored the same way, but printed
     * differently.
     */
    if (strcmp(newNode->type, "array") == 0 ||
        strcmp(newNode->type, "object") == 0) {
        newNode->value = malloc(sizeof(struct List));
        struct List *newNodeList = (struct List *) newNode->value;
        const struct List *argList = (const struct List *) value;
        newNodeList->front = argList->front;
        newNodeList->back = argList->back;
    }

    if (strcmp(newNode->type, "char") == 0) {
        newNode->value = malloc(sizeof(char));
        *((char *) newNode->value) = *(const char *)value;
    }

    if (strcmp(newNode->type, "unsigned") == 0) {
        newNode->value = malloc(sizeof(unsigned));
        *((unsigned *) newNode->value) = *(const unsigned *)value;
    }

    if (newNode->value == NULL) {
        die("malloc failed");
    }

}

/* Return whether list has actual coverage information
 * stored inside.
 */
static int isSubstantialInfo (struct List *list) {
    if (list->front->next == NULL)
        return 0;
    else
        return 1;
}

/* Helper function for printing the data in a struct List. Prints
 * data in the Node and then frees data and Node.
 */
static void printAndDeleteNode (struct Node *node, FILE *file) {
    int moreDataExists = 1;
    struct Node *next = node->next;
    
    // Determine whether to proceed to next recursive call.
    if (next == NULL) {
        moreDataExists = 0;
    }
   
    // If node has array as its value, recursively print List. 
    // Only print List if List is not empty.
    if (strcmp(node->type, "array") == 0 && 
        !isEmptyList((struct List *) node->value)) {
        if (strcmp(node->key, "\"\"") != 0) 
            fprintf(file, "%s: [", node->key);
        else
            fprintf(file, "[");
        struct List *subList = (struct List *) node->value;
        printAndDeleteNode(subList->front, file);
        fprintf(file, "]");
    }
 
    if (strcmp(node->type, "object") == 0 && 
        !isEmptyList((struct List *) node->value)) {
        if (strcmp(node->key, "\"\"") != 0) 
            fprintf(file, "%s: {", node->key);
        else
            fprintf(file, "{");
        struct List *subList = (struct List *) node->value;
        printAndDeleteNode(subList->front, file);
        fprintf(file, "}");
    }
   
    if (strcmp(node->type, "long") == 0) {
       fprintf(file, "%s: %ld", node->key, *(long *) node->value);
    }

    if (strcmp(node->type, "string") == 0) {
        fprintf(file, "%s: %s", node->key, (char *) node->value);
    }

    if (strcmp(node->type, "char") == 0) {
        fprintf(file, "%s: %c", node->key, *(char *) node->value);
    }

    if (strcmp(node->type, "unsigned") == 0) {
        fprintf(file, "%s: %u", node->key, *(unsigned *) node->value);
    }

    // Done printing current node, free allocated data.
    free(node->key);
    free(node->value);
    free(node);

    if (moreDataExists) {
        fprintf(file, ", ");
        printAndDeleteNode(next, file);
    }
}

/* Print elements in a list as a JSON object, deleting them
 * as they are printed. Return 1 if print was successful, 
 * 0 if print was unsuccessful.
 */
int printAndDeleteList (struct List *list, FILE *file) {
    // Don't print anything if list has no coverage info.
    if (!isSubstantialInfo(list)) {
        free(list->front->key);
        free(list->front->value);
        free(list->front);
        return 0;
    }

    fprintf(file, "{");
    printAndDeleteNode(list->front, file);
    fprintf(file, "}");
    fflush(file);
    return 1;
}

